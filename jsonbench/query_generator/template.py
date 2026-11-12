"""Small validated template subset; unsupported syntax fails explicitly."""

import copy
import math
import re

PATH = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")


def field(value):
    if not isinstance(value, str) or not PATH.fullmatch(value):
        raise ValueError(f"Invalid field or identifier: {value!r}")
    return value


def expression(value, *, aggregate=True):
    """Parse one aggregate over a field or size(field), with count(*) special."""
    if not isinstance(value, str):
        raise TypeError("Expression must be a string")
    value = value.strip()
    match = re.fullmatch(r"(\w+)\((.*)\)", value)
    if not match:
        if aggregate:
            raise ValueError("Expected an aggregate expression")
        return ("field", field(value))
    function, argument = match.groups()
    function = function.lower()
    if function == "count" and argument.strip() == "*" and aggregate:
        return ("count", None)
    allowed = {"sum", "avg", "min", "max"} if aggregate else {"size"}
    if function not in allowed:
        raise ValueError(f"Unsupported expression: {value}")
    if function == "size":
        return ("size", ("field", field(argument.strip())))
    return (function, expression(argument, aggregate=False))


def normalize(template):
    result = copy.deepcopy(template)
    primary = field(result["primary_collection"])
    if "." in primary:
        raise ValueError("Collection names must be simple identifiers")
    ops = result["operations"]
    if set(ops) - {"join", "unnest", "match", "group", "project", "sort", "limit"}:
        raise ValueError("Unsupported operation")
    joins = ops.get("join", [])
    joins = joins if isinstance(joins, list) else [joins]
    aliases = {primary}
    for join in joins:
        if set(join) != {"from", "localField", "foreignField"}:
            raise ValueError("Invalid join specification")
        for value in join.values():
            field(value)
        if "." in join["from"] or join["from"] in aliases:
            raise ValueError("Join aliases must be distinct simple identifiers")
        aliases.add(join["from"])
    if joins:
        ops["join"] = joins
    for unnest in ops.get("unnest", []):
        path = unnest["field"] if isinstance(unnest, dict) else unnest
        field(path)
        if isinstance(unnest, dict) and unnest.get("from", primary) != primary:
            source = unnest["from"]
            if not path.startswith(source + "."):
                unnest["field"] = source + "." + path
        if isinstance(unnest, dict) and unnest.get("from", primary) not in aliases:
            raise ValueError("Unknown unnest source")
    for path, value in ops.get("match", {}).items():
        field(path)
        # Until a shared missing/null contract is established, fail closed.
        if value is None or not isinstance(value, (str, bool, int, float)):
            raise ValueError("Only non-null scalar equality predicates are supported")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Predicate numbers must be finite")
    if "group" in ops:
        group = ops["group"]
        by = group["by"] if isinstance(group["by"], list) else [group["by"]]
        if not by:
            raise ValueError("Grouping fields required")
        output = set()
        for path in by:
            alias = field(path).replace(".", "_")
            if alias in output:
                raise ValueError("Colliding group aliases")
            output.add(alias)
        for alias, expr in group["aggregates"].items():
            field(alias)
            if "." in alias or alias in output or alias == "_id":
                raise ValueError("Invalid or colliding aggregate alias")
            expression(expr)
    if "project" in ops:
        if "group" in ops:
            raise ValueError("Post-group projection is not yet supported")
        projection = ops["project"]
        if not isinstance(projection, dict) or not projection:
            raise ValueError("Projection must be a nonempty inclusion mapping")
        for path, include in projection.items():
            field(path)
            if type(include) is not int or include != 1:
                raise ValueError("Only inclusion projections are supported")
    if "sort" in ops:
        sort = ops["sort"]
        if (
            set(sort) != {"field", "direction"}
            or type(sort["direction"]) is not int
            or sort["direction"] not in {-1, 1}
        ):
            raise ValueError("Sort requires field and direction (-1 or 1)")
        field(sort["field"])
        if "group" in ops and sort["field"] not in ops["group"]["aggregates"]:
            raise ValueError("Grouped sorting currently supports aggregate aliases only")
        if "project" in ops and sort["field"] not in ops["project"]:
            raise ValueError("Sort field must be included in projection")
    if "limit" in ops and (type(ops["limit"]) is not int or ops["limit"] <= 0):
        raise ValueError("Limit must be a positive integer")
    return result
