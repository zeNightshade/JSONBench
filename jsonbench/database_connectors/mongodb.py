from pymongo import MongoClient, timeout
from pymongo.errors import PyMongoError

from .outcome import consume


class MongoDB:
    def __init__(self, uri="mongodb://localhost:27017/", database="tour_bookings"):
        self.client = MongoClient(uri)
        client = self.client
        db_name = database

        self.database = client.get_database(db_name)

        self.users = self.database.get_collection("users")
        self.tours = self.database.get_collection("tours")
        self.bookings = self.database.get_collection("bookings")
        self.reviews = self.database.get_collection("reviews")

    def drop_collections(self):
        self.users.drop()
        self.tours.drop()
        self.bookings.drop()
        self.reviews.drop()

    def create_collections(self):
        self.database.create_collection("users")
        self.database.create_collection("tours")
        self.database.create_collection("bookings")
        self.database.create_collection("reviews")

        self.users = self.database.get_collection("users")
        self.tours = self.database.get_collection("tours")
        self.bookings = self.database.get_collection("bookings")
        self.reviews = self.database.get_collection("reviews")

    def create_indexes(self):
        self.bookings.create_index("tour_id")
        self.reviews.create_index("tour_id")

    def load_documents(self, collection, documents):
        self.database[collection].insert_many(documents)

    def close(self):
        self.client.close()

    def query(self, primary_collection, query, *, timeout_seconds=60):
        # PyMongo CSOT covers initial execution and subsequent cursor batches.
        with timeout(timeout_seconds):
            return consume(
                lambda: self.database[primary_collection].aggregate(query),
                errors=(PyMongoError,),
                is_timeout=lambda error: error.timeout,
            )
