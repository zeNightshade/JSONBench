from pymongo import MongoClient

import time


class MongoDB:
    def __init__(self):
        uri = "mongodb://localhost:27017/"
        db_name = "tour_bookings"
        client = MongoClient(uri)

        try:
            self.database = client.get_database(db_name)

            self.users = self.database.get_collection("users")
            self.tours = self.database.get_collection("tours")
            self.bookings = self.database.get_collection("bookings")
            self.reviews = self.database.get_collection("reviews")
        except Exception as e:
            raise Exception("Unable to connect to the MongoDB database due to the following error: ", e)

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
            self.users.insert_one(new_user)
        except Exception as e:
            raise Exception("Unable to add a user to the MongoDB database due to the following error: ", e)
        
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
            self.tours.insert_one(new_tour)
        except Exception as e:
            raise Exception("Unable to add a user to the MongoDB database due to the following error: ", e)
    
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
            self.bookings.insert_one(new_booking)
        except Exception as e:
            raise Exception("Unable to add a user to the MongoDB database due to the following error: ", e)
    
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
            self.reviews.insert_one(new_review)
        except Exception as e:
            raise Exception("Unable to add a user to the MongoDB database due to the following error: ", e)
        
    def query(self, primary_collection, query):
        try:
            if primary_collection == "users":
                results = self.users.aggregate(query)
            elif primary_collection == "tours":
                results = self.tours.aggregate(query)
            elif primary_collection == "bookings":
                results = self.bookings.aggregate(query)
            elif primary_collection == "reviews":
                results = self.reviews.aggregate(query)

            return results
        except Exception as e:
            raise Exception("Unable to query the MongoDB database due to the following error: ", e)
        
    def get_match_field(self, primary_collection, query):
        try:
            start_time = time.perf_counter()
            if primary_collection == "users":
                results = self.users.aggregate(query)
            elif primary_collection == "tours":
                results = self.tours.aggregate(query)
            elif primary_collection == "bookings":
                results = self.bookings.aggregate(query)
            elif primary_collection == "reviews":
                results = self.reviews.aggregate(query)
            end_time = time.perf_counter()

            elapsed_time = end_time - start_time
            return elapsed_time
        except Exception as e:
            raise Exception("Unable to query the MongoDB database due to the following error: ", e)