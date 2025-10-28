import re

class MongoDBQueryGenerator:
    def parse_expr(self, expr: str):
        """
        Parse simple or nested aggregate expressions like:
        - sum(total_price)
        - avg(size(travellers))
        Returns a valid MongoDB aggregation expression.
        """
        expr = expr.strip()
        # Match pattern func(arg)
        match = re.match(r'(\w+)\((.*)\)', expr)
        if not match:
            return f"${expr}"

        func, arg = match.groups()
        func, arg = func.lower().strip(), arg.strip()

        # Handle nested size() or aggregates recursively
        if re.match(r'\w+\(.*\)', arg):
            inner = self.parse_expr(arg)
        elif arg == "*":
            inner = 1  # for count(*)
        else:
            inner = f"${arg}"

        if func == "count":
            func = "sum"
        
        return {f"${func}": inner}

    def generate_query(self, template, match_filter={}):
        operations = template["operations"]
        pipeline = []

        # --- Join (lookup) ---
        if "join" in operations:
            joins = operations["join"] if isinstance(operations["join"], list) else [operations["join"]]
            for join in joins:
                pipeline.append({
                    "$lookup": {
                        "from": join["from"],
                        "localField": join["localField"],
                        "foreignField": join["foreignField"],
                        "as": join["from"]
                    }
                })
                pipeline.append({"$unwind": f"${join['from']}"})

        # --- Unnest (unwind) ---
        if "unnest" in operations:
            for unnest in operations["unnest"]:
                # Support both string and dict formats
                field = unnest["field"] if isinstance(unnest, dict) else unnest
                pipeline.append({"$unwind": f"${field}"})

        # --- Match ---
        if "match" in operations:
            pipeline.append({"$match": match_filter})

        # --- Group ---
        if "group" in operations:
            group = operations["group"]
            by = group["by"]

            # Build _id object for $group, replacing dots in keys
            if isinstance(by, list):
                _id = {b.replace(".", "_"): f"${b}" for b in by}
            else:
                if "." in by:
                    _id = {by.replace(".", "_"): f"${by}"}
                else:
                    _id = f"${by}"

            aggs = {}
            for alias, expr in group["aggregates"].items():
                aggs[alias] = self.parse_expr(expr)

            pipeline.append({"$group": {"_id": _id, **aggs}})
        
        # PROJECT
        if "project" in "operations":
            pipeline.append({"$project": operations["project"]})

        # SORT
        if "sort" in operations:
            sort = operations["sort"]
            pipeline.append({"$sort": {sort["field"]: sort["direction"]}})

        # LIMIT
        if "limit" in operations:
            pipeline.append({"$limit": operations["limit"]})

        return pipeline