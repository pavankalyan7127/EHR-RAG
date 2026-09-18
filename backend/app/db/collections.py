from pymongo.collection import Collection
import gridfs
from app.db.connection import db_manager

# Collection names
PATIENTS_COLLECTION = "patients"
EHR_RECORDS_COLLECTION = "ehr_records"
SESSIONS_COLLECTION = "sessions"
MESSAGES_COLLECTION = "messages"
USERS_COLLECTION = "users"

def get_patients_collection() -> Collection:
    """Returns the 'patients' collection."""
    return db_manager.get_database()[PATIENTS_COLLECTION]

def get_ehr_records_collection() -> Collection:
    """Returns the 'ehr_records' collection."""
    return db_manager.get_database()[EHR_RECORDS_COLLECTION]

def get_sessions_collection() -> Collection:
    """Returns the 'sessions' collection."""
    return db_manager.get_database()[SESSIONS_COLLECTION]

def get_messages_collection() -> Collection:
    """Returns the 'messages' collection."""
    return db_manager.get_database()[MESSAGES_COLLECTION]

def get_users_collection() -> Collection:
    """Returns the 'users' collection."""
    return db_manager.get_database()[USERS_COLLECTION]

def get_gridfs() -> gridfs.GridFS:
    """Returns a GridFS instance bound to the persistent database connection."""
    return gridfs.GridFS(db_manager.get_database())
