# mongo.py
from pymongo import MongoClient
from datetime import datetime

# Connect to local MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client["virtual_closet"]
dolls_collection = db["dolls"]

def save_doll(doll_id: str, name: str, age: int, height: float, weight: float,
              gender: str, skin_color: str, model_type: str, file_path: str):
    """Insert a new doll document"""
    doc = {
        "_id": doll_id,
        "name": name,
        "age": age,
        "height": height,
        "weight": weight,
        "gender": gender,
        "skin_color": skin_color,
        "model_type": model_type,
        "file_path": file_path,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    dolls_collection.insert_one(doc)
    return doc

def get_doll(doll_id: str):
    """Fetch a doll by id"""
    return dolls_collection.find_one({"_id": doll_id})

def update_doll_file(doll_id: str, file_path: str):
    """Update file path after clothing applied"""
    dolls_collection.update_one(
        {"_id": doll_id},
        {"$set": {"file_path": file_path, "updated_at": datetime.utcnow()}}
    )
