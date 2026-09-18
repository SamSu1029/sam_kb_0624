from pymongo import MongoClient

from kb_main.config.config import MongoConfig


mongo_client = None
def get_mongo_client():
    global mongo_client
    if not mongo_client:
        mongo_client = MongoClient(MongoConfig.mongo_url)
    return mongo_client