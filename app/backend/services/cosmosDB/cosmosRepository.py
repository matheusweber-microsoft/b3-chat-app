from azure.cosmos import CosmosClient, PartitionKey
import pymongo
import uuid
from core.log import Logger


class CosmosRepository:
    def __init__(self, connection_string, database_name):
        # A conexão é inicializada usando a connection string
        self.client = pymongo.MongoClient(connection_string)
        self.db = self.client[database_name]
        self.logging = Logger()
        if database_name not in self.client.list_database_names():
            self.logging.error("Database '{}' not found.".format(database_name))
            raise Exception("Database '{}' not found.".format(database_name))
        else:
            print("Using database: '{}'.\n".format(database_name))
        self.logging.info("Connected to database: '{}'.\n".format(database_name))

    def save(self, collection_name, item) -> None:
        collection = self.db.get_collection(collection_name)
        collection.insert_one(item)

    def verify_by_query(self, collection_name, query):
        existing_document = self.db.get_collection(
            collection_name).find_one(query)
        return existing_document is not None

    def get_by_id(self, item_id: uuid.UUID):
        try:
            response = self.container.read_item(
                item=str(item_id), partition_key=str(item_id))
            return response
        except Exception as e:
            return None

    def delete_by_id(self, item_id: uuid.UUID) -> bool:
        try:
            self.container.delete_item(
                item=str(item_id), partition_key=str(item_id))
            return True
        except Exception as e:
            return False

    def list_all(self, collection_name):
        collection = self.db.get_collection(collection_name)
        documents = list(collection.find())
        return documents

    def list_all(self, collection_name, filter, fields, page=1, limit=999):
        collection = self.db.get_collection(collection_name)
        documents = list(collection.find(
            filter, fields).skip((page-1)*limit).limit(limit))
        return documents

    def get_by_id(self, collection_name, item_id):
        collection = self.db.get_collection(collection_name)
        item = collection.find_one({"id": item_id})
        return item
