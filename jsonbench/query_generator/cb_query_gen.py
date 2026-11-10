"""SQL++ compiler for the explicitly validated benchmark subset."""

import json

from .template import expression, normalize


def quoted(path):
    return ".".join(f"`{part}`" for part in path.split("."))


class CouchbaseQueryGenerator:
    def generate_query(self, template):
        template = normalize(template)
        ops = template["operations"]
        primary = template["primary_collection"]
        collections = {primary} | {join["from"] for join in ops.get("join", [])}
        replacements = {}

        def resolve(path):
            for original in sorted(replacements, key=len, reverse=True):
                if path == original or path.startswith(original + "."):
                    return quoted(replacements[original] + path[len(original) :])
            if path.split(".")[0] in collections:
                return quoted(path)
            return quoted(primary + "." + path)

        joins = [
            f"JOIN {quoted(j['from'])} ON {quoted(primary + '.' + j['localField'])} = "
            f"{quoted(j['from'] + '.' + j['foreignField'])}"
            for j in ops.get("join", [])
        ]
        unnests = []
        for index, unnest in enumerate(ops.get("unnest", [])):
            path = unnest["field"] if isinstance(unnest, dict) else unnest
            # Internal aliases cannot collide with collection aliases.
            alias = f"__unnest_{index}"
            while alias in collections:
                alias += "_"
            unnests.append(f"UNNEST {resolve(path)} AS {quoted(alias)}")
            replacements[path] = alias

        def compile_node(node):
            op, arg = node
            if op == "field":
                return resolve(arg)
            if op == "count":
                return "COUNT(*)"
            name = "ARRAY_LENGTH" if op == "size" else op.upper()
            return f"{name}({compile_node(arg)})"

        select = "*"
        group_by = ""
        if "group" in ops:
            group = ops["group"]
            by = group["by"] if isinstance(group["by"], list) else [group["by"]]
            fields = [f"{resolve(path)} AS {quoted(path.replace('.', '_'))}" for path in by]
            fields += [
                f"{compile_node(expression(expr))} AS {quoted(alias)}"
                for alias, expr in group["aggregates"].items()
            ]
            select = ", ".join(fields)
            group_by = "GROUP BY " + ", ".join(resolve(path) for path in by)
        elif "project" in ops:
            select = ", ".join(
                f"{resolve(path)} AS {quoted(path.replace('.', '_'))}" for path in ops["project"]
            )
        parts = [f"SELECT {select} FROM {quoted(primary)}", *joins, *unnests]
        if ops.get("match"):
            # JSON strings are valid SQL++ string literals, including escaped quotes.
            parts.append(
                "WHERE "
                + " AND ".join(
                    f"{resolve(path)} = {json.dumps(value, ensure_ascii=True, allow_nan=False)}"
                    for path, value in ops["match"].items()
                )
            )
        if group_by:
            parts.append(group_by)
        if "sort" in ops:
            sort = ops["sort"]
            key = (
                quoted(sort["field"].replace(".", "_"))
                if "group" in ops or "project" in ops
                else resolve(sort["field"])
            )
            parts.append(f"ORDER BY {key} {'ASC' if sort['direction'] == 1 else 'DESC'}")
        if "limit" in ops:
            parts.append(f"LIMIT {ops['limit']}")
        return " ".join(parts) + ";"
