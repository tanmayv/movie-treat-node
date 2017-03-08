from pymongo import MongoClient
import hashlib
client = MongoClient('mongodb://localhost:27017/')
mydb = client['movie_database']

mydb.movies.drop();
mydb.users.drop();
mydb.user_ratings.drop();

def computeMD5hash(string):
    m = hashlib.md5()
    m.update(string.encode('utf-8'))
    return m.hexdigest()

mydb.users.insert_one({
    "username" : "tanmay",
    "password" : computeMD5hash("tanmay"),
    "moderator" : True,
    "profile_url" : "http://localhost:5000/_uploads/photos/icon_3.png"
})
