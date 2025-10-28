import re


class CouchbaseQueryGenerator:
    def transform_agg_expr(self, expr: str) -> str:
        """
        Convert function expressions (e.g., avg(x), sum(size(y))) to SQL++ compatible syntax.
        """
        expr = expr.strip()
        expr = re.sub(r'\bsize\s*\(\s*([^)]+)\s*\)', r'ARRAY_LENGTH(\1)', expr, flags=re.I)
        expr = re.sub(r'\b(sum|avg|min|max|count)\s*\(', lambda m: m.group(1).upper() + "(", expr, flags=re.I)
        expr = re.sub(r'COUNT\(\s*\*\s*\)', 'COUNT(*)', expr, flags=re.I)
        return expr

    def build_where_clause(self, filter_obj: dict, primary: str) -> str:
        """Build SQL++ WHERE clause from a flat dict like {'a': 1, 'b.c': 'x'}."""
        if not filter_obj:
            return ""
        clauses = []
        for field, value in filter_obj.items():
            qualified = field if "." in field else f"{primary}.{field}"
            if isinstance(value, str):
                val = f"'{value}'"
            elif value is None:
                val = "NULL"
            elif isinstance(value, bool):
                val = "TRUE" if value else "FALSE"
            else:
                val = str(value)
            clauses.append(f"{qualified} = {val}")
        return "WHERE " + " AND ".join(clauses)

    def build_order_clause(self, sort_obj: dict, primary: str) -> str:
        """Convert a sort dict into a SQL++ ORDER BY clause."""
        if not sort_obj:
            return ""
        order_parts = []
        for field, direction in sort_obj.items():
            qualified = field if "." in field else f"{primary}.{field}"
            dir_str = "DESC" if direction in (-1, "desc", "DESC") else "ASC"
            order_parts.append(f"{qualified} {dir_str}")
        return "ORDER BY " + ", ".join(order_parts)

    def generate_query(self, template, match_filter={}):
        operations = template.get("operations", {})
        primary = template.get("primary_collection")
        from_clause = f"FROM {primary}"

        # --- Joins ---
        joins = []
        raw_joins = operations.get("join")
        if raw_joins:
            join_list = raw_joins if isinstance(raw_joins, list) else [raw_joins]
            for join in join_list:
                lhs = f"{primary}.{join['localField']}"
                rhs = f"{join['from']}.{join['foreignField']}"
                joins.append(f"JOIN {join['from']} ON {lhs} = {rhs}")

        # --- Unnests ---
        unnests = []
        if "unnest" in operations:
            for unnest in operations["unnest"]:
                field = unnest["field"] if isinstance(unnest, dict) else unnest
                parts = field.split(".")
                if len(parts) == 1:
                    unnests.append(f"UNNEST {primary}.{parts[0]} AS {parts[0]}")
                else:
                    unnests.append(f"UNNEST {field} AS {parts[-1]}")

                # Adjust group-by list if nested unnests are present
                if "group" in operations:
                    by_list = operations["group"]["by"] if isinstance(operations["group"]["by"], list) else [operations["group"]["by"]]
                    for i, b in enumerate(by_list):
                        if parts[0] in b:
                            by_list[i] = b.lstrip(f"{parts[0]}.")
                
                if "group" in operations:
                        by_list = operations["group"]["by"] if isinstance(operations["group"]["by"], list) else [operations["group"]["by"]]
                        for i, b in enumerate(by_list):
                            if parts[0] in b:
                                by_list[i] = b.lstrip(f"{parts[0]}.")
                elif "project" in operations:
                        updated_proj = {}
                        for alias, val in operations["project"].items():
                            val_str = val if isinstance(val, str) else alias
                            if parts[0] in val_str:
                                val_str = val_str.lstrip(f"{parts[0]}.")
                            updated_proj[alias] = val_str
                        operations["project"] = updated_proj

                if "sort" in operations:
                        updated_sort = {}
                        for s_field, direction in operations["sort"].items():
                            if parts[0] in s_field:
                                s_field = s_field.lstrip(f"{parts[0]}.")
                            updated_sort[s_field] = direction
                        operations["sort"] = updated_sort

        # --- WHERE (dict-style match) ---
        where_clause = ""
        if "match" in operations:
            where_clause = self.build_where_clause(match_filter, primary)

        # --- GROUP + SELECT ---
        select_clause = "SELECT *"
        group_clause = ""
        if "group" in operations:
            group = operations["group"]
            by = group["by"]
            by_list = by if isinstance(by, list) else [by]

            # qualify group-by fields
            group_by_list = [b if "." in b else f"{primary}.{b}" for b in by_list]

            # safe aliasing (replace '.' with '_')
            select_exprs = []
            for b in by_list:
                alias = b.replace(".", "_")
                if "." in b:
                    select_exprs.append(f"{b} AS {alias}")
                else:
                    select_exprs.append(f"{primary}.{b} AS {alias}")

            for alias, agg in group["aggregates"].items():
                select_exprs.append(f"{self.transform_agg_expr(agg)} AS {alias}")

            select_clause = "SELECT " + ", ".join(select_exprs)
            group_clause = "GROUP BY " + ", ".join(group_by_list)

        elif "project" in operations:
            # Project: list of fields
            fields = operations["project"]
            select_exprs = [
                f"{f if '.' in f else f'{primary}.{f}'} AS {f.replace('.', '_')}"
                for f in fields
            ]
            select_clause = "SELECT " + ", ".join(select_exprs)

        # --- SORT & LIMIT ---
        order_clause = self.build_order_clause(operations.get("sort"), primary)
        limit_clause = f"LIMIT {operations['limit']}" if "limit" in operations else ""

        # --- Assemble final query ---
        parts = [select_clause, from_clause]
        parts.extend(joins)
        parts.extend(unnests)
        if where_clause:
            parts.append(where_clause)
        if group_clause:
            parts.append(group_clause)
        if order_clause:
            parts.append(order_clause)
        if limit_clause:
            parts.append(limit_clause)

        return " \n".join(parts) + ";"