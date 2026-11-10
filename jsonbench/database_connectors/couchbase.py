from datetime import timedelta

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import (
    AmbiguousTimeoutException,
    CollectionNotFoundException,
    CouchbaseException,
    TimeoutException,
    UnAmbiguousTimeoutException,
)
from couchbase.options import ClusterOptions, QueryOptions

from .outcome import consume


class Couchbase:
    def __init__(
        self,
        uri="couchbase://localhost",
        username="Administrator",
        password="password",
        bucket="tour_bookings",
        scope="_default",
    ):
        bucket_name = bucket
        self.scope_name = scope
        auth = PasswordAuthenticator(
            username,
            password,
        )

        cluster = Cluster(uri, ClusterOptions(auth))
        self.cluster = cluster

        # Wait until the cluster is ready for use
        try:
            cluster.wait_until_ready(timedelta(seconds=5))
        except CouchbaseException:
            cluster.close()
            raise

        cb = cluster.bucket(bucket_name)
        self.coll_mgr = cb.collections()
        self.query_indexes = cluster.query_indexes()
        self.cb_scope = cb.scope(self.scope_name)

        self.users = self.cb_scope.collection("users")
        self.tours = self.cb_scope.collection("tours")
        self.bookings = self.cb_scope.collection("bookings")
        self.reviews = self.cb_scope.collection("reviews")

    def drop_collections(self):
        for name in ("users", "tours", "bookings", "reviews"):
            try:
                self.coll_mgr.drop_collection(self.scope_name, name)
            except CollectionNotFoundException:
                pass

    def create_collections(self):
        self.coll_mgr.create_collection(self.scope_name, "users")
        self.coll_mgr.create_collection(self.scope_name, "tours")
        self.coll_mgr.create_collection(self.scope_name, "bookings")
        self.coll_mgr.create_collection(self.scope_name, "reviews")

        self.users = self.cb_scope.collection("users")
        self.tours = self.cb_scope.collection("tours")
        self.bookings = self.cb_scope.collection("bookings")
        self.reviews = self.cb_scope.collection("reviews")

    def create_indexes(self):
        self.cb_scope.query("CREATE INDEX `tours-id` ON tours(_id);").execute()
        self.cb_scope.query("CREATE INDEX `bookings-tour_id` ON bookings(tour_id);").execute()
        self.cb_scope.query("CREATE INDEX `reviews-tour_id` ON reviews(tour_id);").execute()
        for collection, name in [
            ("tours", "tours-id"),
            ("bookings", "bookings-tour_id"),
            ("reviews", "reviews-tour_id"),
        ]:
            self.cb_scope.collection(collection).query_indexes().watch_indexes(
                [name], timeout=timedelta(seconds=300)
            )

    def load_documents(self, collection, documents):
        destination = self.cb_scope.collection(collection)
        for document in documents:
            destination.upsert(document["_id"], document)

    def close(self):
        self.cluster.close()

    def query(self, primary_collection, query, *, timeout_seconds=60):
        return consume(
            lambda: self.cb_scope.query(
                query, QueryOptions(timeout=timedelta(seconds=timeout_seconds))
            ),
            errors=(CouchbaseException,),
            is_timeout=lambda error: isinstance(
                error, (TimeoutException, AmbiguousTimeoutException, UnAmbiguousTimeoutException)
            ),
        )
