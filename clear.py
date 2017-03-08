from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
mydb = client['movie_database']
mydb.movies.drop()
