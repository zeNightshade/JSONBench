from jsonbench.database_connectors import mongodb
from jsonbench.database_connectors import couchbase

from jsonbench.query_generator import mdb_query_gen
from jsonbench.query_generator import cb_query_gen

import json


class ConfigLoader:
    def __init__(self, path="jsonbench/src/config.json"):
        self.path = path

        with open(self.path) as f:
            config = json.load(f)

            if config["database"] == "mongodb":
                self.database = mongodb.MongoDB()
                self.query_gen = mdb_query_gen.MongoDBQueryGenerator()
            elif config["database"] == "couchbase":
                self.database = couchbase.Couchbase()
                self.query_gen = cb_query_gen.CouchbaseQueryGenerator()
            else:
                raise Exception("Invalid database in configuration file!")
            
            self.database_type = config["database"]
            self.generate_data = config["generate_data"]
            self.create_indexes = config["create_indexes"]
            self.scale_factor = float(config["scale_factor"])
            self.workers = int(config["workers"])
            self.duration = int(config["duration"])
            self.query_template_path = config["query_template_path"]
            self.query_sel_prob = config["query_selection_probability"]
            
    def get_database(self):
        return self.database
    
    def get_database_type(self):
        return self.database_type
    
    def get_query_gen(self):
        return self.query_gen
    
    def get_generate_data(self):
        return self.generate_data
    
    def get_create_indexes(self):
        return self.create_indexes
    
    def get_scale_factor(self):
        return self.scale_factor
    
    def get_workers(self):
        return self.workers
    
    def get_duration(self):
        return self.duration
    
    def get_query_template_path(self):
        return self.query_template_path
    
    def get_query_sel_prob(self):
        return self.query_sel_prob
    
    def display_config(self):
        if self.generate_data:
            print(f"Database: {self.database_type}, create indexes: {self.create_indexes}, scale factor: {self.scale_factor}")
        else:
            print(f"Database: {self.database_type}, workers: {self.workers}, duration: {self.duration}, query selection probability: {self.query_sel_prob}")