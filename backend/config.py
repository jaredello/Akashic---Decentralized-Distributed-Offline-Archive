"""Settings shared by the whole backend: database connection, logging and the disc hardware we model.

Everything secret or environment-specific (database address, storage key) comes from backend/.env.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("offline-wiki")

# MongoDB. The "text_disk" collection plays the Text Disc, "media_disk" plays the Media Disc.
mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = mongo_client[os.environ["DB_NAME"]]

# The real-world hardware this demo stands in for.
DISC_CAPACITY_BYTES = 100 * 1000 * 1000 * 1000  # one Verbatim 100 GB M-DISC
DRIVE_MODEL = "ASUS ZenDrive U9M"
DISC_MEDIUM = "Verbatim M-DISC BD-R 100GB"

# Where finished disc images go when object storage is unavailable.
LOCAL_EXPORT_DIR = Path("/tmp/offline_wiki_exports")
