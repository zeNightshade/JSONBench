"""Generate canonical JSONL datasets without database connections."""

import hashlib
import json
import math
import random
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

from faker import Faker


class DatasetGenerator:
    def __init__(self, *, seed, reference_date):
        self.rng = random.Random(seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed)
        self.reference = date.fromisoformat(reference_date)
        self.seed = seed

    def records(self, scale):
        if (
            isinstance(scale, bool)
            or not isinstance(scale, (int, float))
            or not math.isfinite(scale)
            or scale < 0.01
        ):
            raise ValueError("Scale factor must be finite and at least 0.01")
        # State is local to this invocation; instantiate a fresh generator per artifact.
        users, guides, tours, bookings = [], [], [], []
        fake, rng = self.fake, self.rng
        count = int(1000 * scale)
        for index in range(count):
            identity = f"user-{index}"
            role = "guide" if index >= int(count * 0.9) else "user"
            (guides if role == "guide" else users).append(identity)
            yield (
                "users",
                {
                    "_id": identity,
                    "name": fake.name(),
                    "email": fake.email(),
                    "password": fake.password(16),
                    "role": role,
                    "gender": rng.choice(["F", "M", "X"]),
                    "nationality": fake.country(),
                },
            )
        for index in range(int(200 * scale)):
            duration = rng.randint(1, 31)
            start = self.reference - timedelta(days=rng.randint(duration, 3650))
            itinerary, day = [], 0
            while day < duration:
                itinerary.append(
                    {"location": fake.city(), "date": (start + timedelta(days=day)).isoformat()}
                )
                day += rng.randint(1, max(1, duration // 4))
            tour = {
                "_id": f"tour-{index}",
                "name": fake.name(),
                "description": fake.text(500),
                "difficulty": rng.choices(["easy", "intermediate", "hard"], [0.5, 0.35, 0.15])[0],
                "duration": duration,
                "max_group_size": rng.randint(10, 100),
                "rrp": round(rng.uniform(100, 10000), 2),
                "departure": fake.country(),
                "destination": fake.country(),
                "itinerary": itinerary,
                "guide_id": rng.choice(guides),
            }
            tours.append((tour["_id"], tour["rrp"]))
            yield "tours", tour
        for index in range(int(5000 * scale)):
            tour, price = rng.choice(tours)
            travellers = [
                {
                    "name": fake.name(),
                    "age": rng.randint(1, 100),
                    "gender": rng.choice(["F", "M", "X"]),
                    "nationality": fake.country(),
                }
                for _ in range(rng.randint(1, 10))
            ]
            when = self.reference - timedelta(days=rng.randint(1, 3650))
            identity = f"booking-{index}"
            bookings.append((identity, tour, when))
            yield (
                "bookings",
                {
                    "_id": identity,
                    "user_id": rng.choice(users),
                    "tour_id": tour,
                    "travellers": travellers,
                    "total_price": round(price * len(travellers), 2),
                    "date": when.isoformat(),
                    "paid": rng.random() < 0.8,
                    "travelled": rng.random() < 0.75,
                },
            )
        for index in range(int(2500 * scale)):
            booking, tour, when = rng.choice(bookings)
            review_date = when + timedelta(days=rng.randint(1, (self.reference - when).days))
            yield (
                "reviews",
                {
                    "_id": f"review-{index}",
                    "booking_id": booking,
                    "tour_id": tour,
                    "rating": rng.randint(1, 5),
                    "review": fake.text(2000),
                    "date": review_date.isoformat(),
                },
            )


def generate_dataset(path, *, scale, seed, reference_date):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    counts = {}
    generator = DatasetGenerator(seed=seed, reference_date=reference_date)
    handles = {}
    try:
        for collection, record in generator.records(scale):
            if collection not in handles:
                handles[collection] = (path / f"{collection}.jsonl").open("w")
            handles[collection].write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            counts[collection] = counts.get(collection, 0) + 1
    finally:
        for handle in handles.values():
            handle.close()
    files = {}
    for collection, count in counts.items():
        file = path / f"{collection}.jsonl"
        with file.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        files[collection] = {"count": count, "bytes": file.stat().st_size, "sha256": digest}
    manifest = {
        "format_version": 1,
        "generator_version": 1,
        "seed": seed,
        "reference_date": reference_date,
        "scale_factor": scale,
        "faker_version": version("Faker"),
        "collections": files,
    }
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def validate_dataset(path):
    """Preflight the entire artifact before any destructive database operation."""
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    if not isinstance(manifest, dict) or type(manifest.get("format_version")) is not int:
        raise ValueError("Invalid dataset manifest")
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported dataset format version")
    collections = manifest.get("collections")
    if not isinstance(collections, dict) or set(collections) != {
        "users", "tours", "bookings", "reviews"
    }:
        raise ValueError("Dataset must contain exactly the four benchmark collections")

    for collection, metadata in collections.items():
        if not isinstance(metadata, dict) or any(
            type(metadata.get(key)) is not int or metadata[key] < 0
            for key in ("count", "bytes")
        ):
            raise ValueError(f"Invalid dataset metadata: {collection}")
        file_path = path / f"{collection}.jsonl"
        with file_path.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != metadata.get("sha256"):
                raise ValueError(f"Dataset checksum mismatch: {collection}")
        if file_path.stat().st_size != metadata["bytes"]:
            raise ValueError(f"Dataset byte size mismatch: {collection}")

        # Duplicate IDs would be overwritten by Couchbase but rejected by MongoDB.
        identities = set()
        count = 0
        with file_path.open() as file:
            for count, line in enumerate(file, 1):
                try:
                    record = json.loads(line, parse_constant=_reject_json_constant)
                except ValueError as exc:
                    raise ValueError(f"Invalid JSON in {collection}, line {count}") from exc
                if not isinstance(record, dict) or not isinstance(record.get("_id"), str):
                    raise ValueError(f"Document requires a string _id: {collection}, line {count}")
                identity = record["_id"]
                if not identity or len(identity.encode("utf-8")) > 250:
                    raise ValueError(f"Document _id exceeds shared key contract: {collection}")
                if identity in identities:
                    raise ValueError(f"Duplicate document _id: {collection}, line {count}")
                identities.add(identity)
        if count != metadata["count"]:
            raise ValueError(f"Dataset record count mismatch: {collection}")
    return manifest


def _reject_json_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def load_dataset(config):
    path = Path(config.settings["dataset_directory"])
    manifest = validate_dataset(path)
    if config.settings.get("replace_collections") is not True:
        raise ValueError(
            "Loading requires explicit replace_collections=true for benchmark-owned collections"
        )
    database = config.get_database()
    database.ensure_ownership()
    database.drop_collections()
    database.create_collections()
    for collection in manifest["collections"]:
        with (path / f"{collection}.jsonl").open() as file:
            batch = []
            for line in file:
                batch.append(json.loads(line))
                if len(batch) == 500:
                    database.load_documents(collection, batch)
                    batch = []
            if batch:
                database.load_documents(collection, batch)
    if config.get_create_indexes():
        database.create_indexes()
    return manifest


def main(config):
    settings = config.settings
    return generate_dataset(
        settings["dataset_directory"],
        scale=config.get_scale_factor(),
        seed=settings["seed"],
        reference_date=settings["reference_date"],
    )
