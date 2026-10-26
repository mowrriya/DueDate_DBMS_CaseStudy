import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["DueDate"]

users_collection = db["users"]
subjects_collection = db["subjects"]
assignments_collection = db["assignments"]


def initialize_database():
    """Verify MongoDB, create useful indexes, and add starter subjects."""
    client.admin.command("ping")

    users_collection.create_index([("email", ASCENDING)], unique=True)
    subjects_collection.create_index([("name", ASCENDING)], unique=True)
    assignments_collection.create_index(
        [("owner_id", ASCENDING), ("due_date", ASCENDING)]
    )
    assignments_collection.create_index(
        [("owner_id", ASCENDING), ("status", ASCENDING)]
    )
    assignments_collection.create_index([("subject_id", ASCENDING)])

    starter_subjects = [
        {"name": "Database Management Systems", "code": "DBMS"},
        {"name": "Data Structures and Algorithms", "code": "DSA"},
        {"name": "Python Programming", "code": "PY"},
        {"name": "Digital Electronics", "code": "DE"},
        {"name": "Mathematics", "code": "MATH"},
        {"name": "Other", "code": "OTHER"},
    ]

    for subject in starter_subjects:
        subjects_collection.update_one(
            {"name": subject["name"]},
            {"$setOnInsert": subject},
            upsert=True,
        )

    print("MongoDB connection successful.")
    print("Database: DueDate")


def ping_database():
    try:
        client.admin.command("ping")
        return True
    except PyMongoError:
        return False
