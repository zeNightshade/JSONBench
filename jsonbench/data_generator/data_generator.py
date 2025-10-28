from alive_progress import alive_it
from faker import Faker
from datetime import datetime, timedelta

import numpy as np

import bcrypt
import random


fake = Faker()

users = []
guides = []
tours = []
bookings = []

def generate_users(database, scale_factor):
    print("> Generating users data...")
    
    num_docs = int(1000 * scale_factor)
    for _ in alive_it(range(num_docs)):
        id = fake.unique.md5()
        name = fake.name()
        email = fake.email()
        password = bcrypt.hashpw(fake.password(16).encode(), bcrypt.gensalt()).decode()
        gender = fake.passport_gender()
        nationality = fake.country()

        if _ >= (num_docs * 0.9):
            role = "guide"
            guides.append(id)
        else:
            role = "user"
            users.append(id)

        database.add_user(
            id, name, email, password,
            role, gender, nationality
        )

    print("> Users data generated successfully!")

def generate_itinerary(duration):
    itinerary = []
    start_date = fake.date_between(start_date=datetime.today()-timedelta(days=3650))
    _ = 0
    while _ < duration:
        location = fake.city()
        date = (start_date + timedelta(days=_)).strftime("%Y-%m-%d")

        itinerary.append({
            "location": location,
            "date": date
        })

        _ += random.randint(1, max(1, int(duration/4)))
        
    return itinerary
        
def generate_tours(database, scale_factor):
    print("> Generating tours data...")

    num_docs = int(100 * scale_factor)
    for _ in alive_it(range(num_docs)):
        id = fake.unique.md5()
        name = fake.name()
        description = fake.text(500)
        difficulty = str(np.random.choice(["easy", "intermediate", "difficult"], p=[0.5, 0.35, 0.15]))
        duration = random.randint(1, 31)
        max_size = random.randint(10, 100)
        price = round(random.uniform(100, 10000), 2)
        departure = fake.country()
        destination = fake.country()
        itinerary = generate_itinerary(duration)
        guide_id = random.choice(guides)

        tours.append({
            "tour_id": id,
            "price": price
            })
        
        database.add_tour(
            id, name, description,
            difficulty, duration, max_size,
            price, departure, destination,
            itinerary, guide_id
        )

    print("> Tours data generated successfully!")

def generate_travellers():
    travellers = []
    for _ in range(random.randint(1, 10)):
        name = fake.name()
        age = random.randint(1, 100)
        gender = fake.passport_gender()
        nationality = fake.country()

        travellers.append({
            "name": name,
            "age": age,
            "gender": gender,
            "nationality": nationality
        })
    
    return travellers
    

def generate_bookings(database, scale_factor):
    print("> Generating bookings data...")

    num_docs = int(5000 * scale_factor)
    for _ in alive_it(range(num_docs)):
        tour = random.choice(tours)

        id = fake.unique.md5()
        user_id = random.choice(users)
        tour_id = tour["tour_id"]
        travellers = generate_travellers()
        total_price = len(travellers) * tour["price"]
        date = fake.date_between(start_date=datetime.today()-timedelta(days=3650)).strftime("%Y-%m-%d")
        paid = bool(np.random.choice([True, False], p=[0.8, 0.2]))
        travelled = bool(np.random.choice([True, False], p=[0.75, 0.25]))

        bookings.append({
            "booking_id": id,
            "user_id": user_id,
            "tour_id": tour_id,
            "date": datetime.strptime(date, "%Y-%m-%d")
        })

        database.add_booking(
            id, user_id, tour_id,
            travellers, total_price, date,
            paid, travelled
        )

    print("> Bookings data generated successfully!")

def generate_reviews(database, scale_factor):
    print("> Generating reviews data...")

    num_docs = int(2500 * scale_factor)
    for _ in alive_it(range(num_docs)):
        booking = random.choice(bookings)

        id = fake.unique.md5()
        booking_id = booking["booking_id"]
        tour_id = booking["tour_id"]
        rating = random.randint(1, 5)
        review = fake.text(2000)
        date = fake.date_between(start_date=booking["date"]).strftime("%Y-%m-%d")

        database.add_review(
            id, booking_id, tour_id,
            rating, review, date
        )

    print("> Reviews data generated successfully!")

def main(config):
    database = config.get_database()
    scale_factor = config.get_scale_factor()

    print("> Starting data generation and loading process...")
    print("-" * 50)
    
    print("> Clearing existing data and dropping existing collections...")
    database.drop_collections()
    print("> Creating collections...")
    database.create_collections()

    generate_users(database, scale_factor)
    generate_tours(database, scale_factor)
    generate_bookings(database, scale_factor)
    generate_reviews(database, scale_factor)

    print("> Data generation and loading completed successfully!")