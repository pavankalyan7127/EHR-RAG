import re
import logging
from typing import Optional
from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, PyMongoError
from app.config import MONGODB_URI, MONGODB_DATABASE

logger = logging.getLogger(__name__)

def mask_mongodb_uri(uri: str) -> str:
    """Masks credentials in MongoDB connection string for safe logging."""
    if not uri:
        return ""
    # Matches ://<user>:<password>@ and replaces with ://<user>:****@
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", uri)

class MongoDBManager:
    """
    Manages the persistent MongoDB client connection lifecycle.
    Avoids recreating MongoClient instances across requests.
    """
    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> Database:
        """
        Initializes MongoClient, verifies connectivity with a ping,
        and creates standard collection indexes.
        """
        if self._db is not None and self._client is not None:
            return self._db

        if not MONGODB_URI or not MONGODB_URI.strip():
            logger.error("MONGODB_URI is not set in environment or .env file.")
            raise ValueError(
                "MONGODB_URI is missing. Please configure MONGODB_URI in your .env file or environment variables."
            )

        masked_uri = mask_mongodb_uri(MONGODB_URI)
        logger.info(f"Connecting to MongoDB database '{MONGODB_DATABASE}' via {masked_uri}...")

        try:
            # serverSelectionTimeoutMS ensures quick failure if cluster is unreachable
            self._client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                appname="EHR_RAG_FastAPI"
            )
            # Verify connectivity via admin ping
            self._client.admin.command("ping")
            self._db = self._client[MONGODB_DATABASE]
            logger.info(f"MongoDB connection established successfully to database '{MONGODB_DATABASE}'.")

            # Ensure indexes on startup
            self.init_indexes()
            return self._db

        except ConnectionFailure as cf:
            logger.error(f"MongoDB connection verification failed: {cf}")
            self.disconnect()
            raise RuntimeError(f"Could not connect to MongoDB Atlas. Connection failure: {cf}") from cf
        except PyMongoError as pe:
            logger.error(f"MongoDB error during initialization: {pe}")
            self.disconnect()
            raise RuntimeError(f"MongoDB initialization error: {pe}") from pe
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            self.disconnect()
            raise

    def disconnect(self):
        """Closes the MongoDB client connection cleanly."""
        if self._client is not None:
            logger.info("Closing MongoDB client connection.")
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error while closing MongoDB client: {e}")
            finally:
                self._client = None
                self._db = None

    def get_database(self) -> Database:
        """Returns active Database instance or raises RuntimeError if not connected."""
        if self._db is None:
            return self.connect()
        return self._db

    def is_connected(self) -> bool:
        """Checks if client is active and can ping the database."""
        if self._client is None or self._db is None:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    def init_indexes(self):
        """
        Creates required indexes for collections:
        - patients: _id (default), name
        - ehr_records: patient_id, (patient_id, chunk_id)
        - sessions: patient_id, updated_at
        - messages: session_id, (session_id, timestamp)
        """
        if self._db is None:
            return

        try:
            # Patients indexes
            self._db["patients"].create_index([("name", ASCENDING)], background=True)

            # EHR Records indexes
            self._db["ehr_records"].create_index([("patient_id", ASCENDING)], background=True)
            self._db["ehr_records"].create_index(
                [("patient_id", ASCENDING), ("chunk_id", ASCENDING)],
                unique=True,
                background=True
            )

            # Sessions indexes
            self._db["sessions"].create_index([("patient_id", ASCENDING)], background=True)
            self._db["sessions"].create_index([("updated_at", ASCENDING)], background=True)

            # Messages indexes
            self._db["messages"].create_index([("session_id", ASCENDING)], background=True)
            self._db["messages"].create_index(
                [("session_id", ASCENDING), ("timestamp", ASCENDING)],
                background=True
            )

            logger.info("MongoDB collection indexes verified/created successfully.")
        except Exception as e:
            logger.warning(f"Failed to create MongoDB indexes: {e}")

db_manager = MongoDBManager()
