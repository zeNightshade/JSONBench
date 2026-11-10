"""Ownership applies only to the four benchmark collections in one namespace."""

COLLECTIONS = {"users", "tours", "bookings", "reviews"}
MARKER_COLLECTION = "jsonbench_metadata"
MARKER_KEY = "ownership"
MARKER = {"owner": "JSONBench", "format_version": 1, "collections": sorted(COLLECTIONS)}


def validate_ownership(names, marker):
    if marker is not None:
        if marker != MARKER:
            raise ValueError("Destination has an unrecognised JSONBench ownership marker")
        return
    if names:
        raise ValueError(
            "Refusing to replace an unowned destination; choose a new empty database/scope"
        )
