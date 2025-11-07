from datetime import timedelta

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import CollectionNotFoundException
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions)

import time


class Couchbase:
    def __init__(self):
        uri = "couchbase://localhost"
        username = "Administrator"
        password = "password"
        bucket_name = "tour_bookings"
        self.scope_name = "_default"
        auth = PasswordAuthenticator(
            username,
            password,
        )

        cluster = Cluster(uri, ClusterOptions(auth))

        # Wait until the cluster is ready for use
        cluster.wait_until_ready(timedelta(seconds=5))

        cb = cluster.bucket(bucket_name)
        self.coll_mgr = cb.collections()
        self.query_indexes = cluster.query_indexes()
        self.cb_scope = cb.scope(self.scope_name)

        self.users = self.cb_scope.collection("users")
        self.tours = self.cb_scope.collection("tours")
        self.bookings = self.cb_scope.collection("bookings")
        self.reviews = self.cb_scope.collection("reviews")

    def drop_collections(self):
        try:
            self.coll_mgr.drop_collection(self.scope_name, "users")
            self.coll_mgr.drop_collection(self.scope_name, "tours")
            self.coll_mgr.drop_collection(self.scope_name, "bookings")
            self.coll_mgr.drop_collection(self.scope_name, "reviews")
        except CollectionNotFoundException:
            pass
        except Exception as e:
            raise Exception("Unable to drop collections in the Couchbase database due to the following error: ", e)

    def create_collections(self):
        try:
            self.coll_mgr.create_collection(self.scope_name, "users")
            self.coll_mgr.create_collection(self.scope_name, "tours")
            self.coll_mgr.create_collection(self.scope_name, "bookings")
            self.coll_mgr.create_collection(self.scope_name, "reviews")

            self.users = self.cb_scope.collection("users")
            self.tours = self.cb_scope.collection("tours")
            self.bookings = self.cb_scope.collection("bookings")
            self.reviews = self.cb_scope.collection("reviews")
        except Exception as e:
            raise Exception("Unable to create collections in the Couchbase database due to the following error: ", e)
        
    def create_indexes(self):
        try:
            self.cb_scope.query("CREATE INDEX `bookings-tour_id` ON bookings(tour_id);").execute()
            self.cb_scope.query("CREATE INDEX `reviews-tour_id` ON reviews(tour_id);").execute()
        except Exception as e:
            raise Exception("Unable to create indexes in the Couchbase database due to the following error: ", e)

    def add_user(self, id, name, email, password, role, gender, nationality):
        try:
            new_user = {
                "_id": id,
                "name": name,
                "email": email,
                "password": password,
                "role": role,
                "gender": gender,
                "nationality": nationality
            }
            self.users.upsert(id, new_user)
        except Exception as e:
            raise Exception("Unable to add a user to the Couchbase database due to the following error: ", e)
        
    def add_tour(self, id, name, description, difficulty, duration, max_size, price, departure, destination, itinerary, guide_id):
        try:
            new_tour = {
                "_id": id,
                "name": name,
                "description": description,
                "difficulty": difficulty,
                "duration": duration,
                "max_group_size": max_size,
                "rrp": price,
                "departure": departure,
                "destination": destination,
                "itinerary": itinerary,
                "guide_id": guide_id
                
            }
            self.tours.upsert(id, new_tour)
        except Exception as e:
            raise Exception("Unable to add a user to the Couchbase database due to the following error: ", e)
    
    def add_booking(self, id, user_id, tour_id, travellers, total_price, date, paid, travelled):
        try:
            new_booking = {
                "_id": id,
                "user_id": user_id,
                "tour_id": tour_id,
                "travellers": travellers,
                "date": date,
                "total_price": total_price,
                "paid": paid,
                "travelled": travelled
            }
            self.bookings.upsert(id, new_booking)
        except Exception as e:
            raise Exception("Unable to add a user to the Couchbase database due to the following error: ", e)
    
    def add_review(self, id, booking_id, tour_id, rating, review, date):
        try:
            new_review = {
                "_id": id,
                "booking_id": booking_id,
                "tour_id": tour_id,
                "rating": rating,
                "review": review,
                "date": date
            }
            self.reviews.upsert(id, new_review)
        except Exception as e:
            raise Exception("Unable to add a user to the Couchbase database due to the following error: ", e)
        
    def query(self, primary_collection, query):
        try:
            start_time = time.perf_counter()
            results = self.cb_scope.query(query)
            for row in results:
                end_time = time.perf_counter()

            elapsed_time = end_time - start_time
            return elapsed_time
        except Exception as e:
            raise Exception("Unable to query the Couchbase database due to the following error: ", e)