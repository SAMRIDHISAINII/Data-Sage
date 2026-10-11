import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
datasets_col = db["datasets"]
messages_col = db["messages"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    return out
