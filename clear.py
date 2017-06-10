from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
mydb = client['cover']
mydb.movies.drop()
