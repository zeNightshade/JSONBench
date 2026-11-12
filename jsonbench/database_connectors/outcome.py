"""Common fully consumed query outcome; no database imports needed."""

from time import perf_counter


def consume(operation, *, errors, is_timeout, clock=perf_counter):
    """Time submission and full consumption, preserving database failures."""
    start = clock()
    rows = None
    try:
        rows = operation()
        count = sum(1 for _ in rows)
        return {"status": "success", "time": clock() - start, "row_count": count, "error": None}
    except errors as error:
        return {
            "status": "timeout" if is_timeout(error) else "error",
            "time": clock() - start,
            "row_count": None,
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    finally:
        if rows is not None and hasattr(rows, "close"):
            rows.close()
