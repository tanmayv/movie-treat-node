from flask import Flask, jsonify, request, send_from_directory
import omdb;
from pymongo import MongoClient
import math;
import datetime
import hashlib
from flask_uploads import (UploadSet, configure_uploads, IMAGES,
                              UploadNotAllowed)
import numpy as np
from sklearn.decomposition import ProjectedGradientNMF

# App

UPLOADED_PHOTOS_DEST = '/tmp/photolog'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__, static_url_path='')


# Global Vars
photos = UploadSet('photos', IMAGES,default_dest=lambda app:app.instance_path)
configure_uploads(app, photos)
count = 0
user_count = 0
batch_size = 12
client = MongoClient('mongodb://localhost:27017/')
mydb = client['movie_database']
user_rating_matrix = []
movie_index_dict = {}
user_index_dict = {}

def init_user_rating_matrix():
    user_rating_cursor = mydb.user_ratings.find()

    for user_rating_item in user_rating_cursor:
        insert_into_matrix(user_rating_item.get("user_id"), user_rating_item.get("movie_id"), user_rating_item.get("rating"))

def convert_to_numpy(list_matrix):
    max_len = len(max(list_matrix,key=len))
    for list_item in list_matrix:
        current_len = len(list_item)
        for i in xrange(max_len - current_len):
            list_item.append(0)
    return np.array(list_matrix)


def key_from_value(value, dict):
    for key in dict.keys():
        if(dict.get(key) == value):
            return key

def insert_into_matrix(user_id, movie_id, rating):
    matrix_len = len(user_rating_matrix)

    user_index = get_item_index(user_id, user_index_dict)
    movie_index = get_item_index(movie_id, movie_index_dict)
    if user_index >= matrix_len:
        itr_count = user_index - matrix_len + 1
        for i in xrange(itr_count):
            user_rating_matrix.append([])
    tempArray = user_rating_matrix[user_index]
    tempArray_len = len(tempArray)
    if movie_index < tempArray_len:
        tempArray[movie_index] = rating
    else:
        itr_count = movie_index - tempArray_len
        for i in xrange(itr_count):
            tempArray.append(0)
        tempArray.append(rating)
    user_rating_matrix[user_index] = tempArray


def get_item_index(item_id, dict):
    if item_id in dict.keys():
        return dict[item_id]
    else:

        current_length = len(dict)
        dict[item_id] = current_length
        return current_length
# Routes
@app.route('/_uploads/photos/<path:path>')
def send_js(path):
    return send_from_directory('instance', path)

@app.route('/')
def index():
    return "Hello, World!"

@app.route('/login', methods=['POST'])
def login():
    content = request.get_json(force=True)
    print content
    username = content.get("username", None)
    password = content.get("password", None)
    password = computeMD5hash(password)
    print username

    user = mydb.users.find_one({"_id" : username, "password" : password});
    if user :
        valid = True;
        return jsonify({"valid" : valid, "mod" : user.get("moderator")})
    else:
        return jsonify({"valid" : False})

@app.route('/rateMovie', methods=["POST"])
def rateMovie():
    content = request.get_json(force=True)
    print content
    username = content.get("username", None)
    movie_id = content.get("movie_id", None)
    valid_user = mydb.users.find_one({"_id" : username});
    valid_movie = mydb.movies.find_one({"_id": movie_id})

    if not valid_user or not valid_movie:
        return jsonify({"message" : "Invalid User or Movie"})

    rating = content.get("rating", 0)
    if username and movie_id and rating :
        rating_item = mydb.user_ratings.find_one({"user_id" : username, "movie_id" : movie_id});
        if rating_item :
            mydb.user_ratings.update_one({"_id" : rating_item.get("_id")}, {"$set": {"rating" : rating, "time_stamp" : datetime.datetime.now().isoformat()}})
            createActivity(valid_user.get("profile_url"),username, "rated", valid_movie.get("title"), rating)

        else:
            mydb.user_ratings.insert_one({"user_id" : username, "movie_id" : movie_id,"rating": rating, "time_stamp" : datetime.datetime.now().isoformat()})
            createActivity(valid_user.get("profile_url"),username, "rated", valid_movie.get("title"), rating)
        insert_into_matrix(username, movie_id, rating)
        convert_to_numpy(user_rating_matrix)
        return jsonify({"message" : "success"})
    else:
        return jsonify({"message" : "failure"})

@app.route('/register', methods=["POST"])
def register():
    content = request.get_json(force=True)
    print content
    username = content.get("username", None)
    password = content.get("password", None)
    moderator = content.get("moderator", False)
    print moderator
    url =  content.get("profile_url", None)
    if request.method == 'POST' and 'photo' in request.files:
        filename = photos.save(request.files['photo'])
        url = photos.url(filename)

    password = computeMD5hash(password)
    if moderator :
        moderator = True
    user = mydb.users.find_one({"_id" : username});
    if user:
        return jsonify({"message" : "User Already Exists!"})
    else :
        valid = True
        mydb.users.insert_one({
            "_id" : username,
            "password" : password,
            "moderator" : moderator,
            "time_stamp" : datetime.datetime.now().isoformat(),
            "profile_url" : url
        })
    return jsonify({"message" : "success"})

@app.route('/save_movie/<string:id>')
def saveMovie(id):
    result = mydb.movies.find({"_id" : id})
    if count_iterable(result) < 1:
        movieInfo = omdb.imdbid(id)
        movieInfo["_id"] = movieInfo["imdb_id"]
        movieInfo["time_stamp"] = datetime.datetime.now().isoformat();
        mydb.movies.insert_one(movieInfo)
        print movieInfo.title +" Inserted!"
        calculate_movies_count();
    return jsonify({"message" : "success"})

@app.route('/recommend/<string:id>')
def recommend(id):
    A = convert_to_numpy(user_rating_matrix)
    nmf_model = ProjectedGradientNMF(n_components = 5, init='random', random_state=0)
    W = nmf_model.fit_transform(A);
    H = nmf_model.components_;

    i = get_item_index(id, user_index_dict)
    nR = np.dot(W, H)
    a = nR[i].tolist()
    max_i =  np.argsort(a)[::-1][:5]
    result = {}
    max_i = max_i.tolist()

    index = len(max_i);
    while index > 0:
        print a[index - 1]
        result[key_from_value(index -1 , movie_index_dict)] = a[index - 1]
        index = index - 1

    return jsonify(result)
@app.route('/delete_movie/<string:id>')
def deleteMovie(id):
    result = mydb.movies.find({"_id" : id})
    if count_iterable(result) > 0:
        movieInfo = omdb.imdbid(id)
        movieInfo["_id"] = movieInfo["imdb_id"]
        mydb.movies.delete_many({"_id" : id})
        print movieInfo.title +" Deleted!"
        calculate_movies_count();
    return jsonify({"message" : "success"})

@app.route('/movies/<int:page_no>')
def get_movies(page_no ):
    if get_movies_count() < 1:
        calculate_movies_count();

    if request.args :
        username = request.args.get("username", None)
    print username
    ratedMovies = []
    if username:
        movie_iter = mydb.user_ratings.find({"user_id" : username})
        for movie in movie_iter:
            print movie
            ratedMovies.append(movie)

    movies = mydb.movies.find().sort("time_stamp", -1).skip((page_no - 1) * batch_size).limit(batch_size)
    result = []
    for movie in movies:
        rating_item = isInArray(ratedMovies, movie, "movie_id", "_id")
        if rating_item:
            movie["user_rating"]=rating_item.get("rating")
        result.append(movie)
    return jsonify({"count": get_movies_count(), "movies": result})

@app.route('/users/<int:page_no>')
def get_users(page_no ):
    if get_users_count() < 1:
        calculate_users_count();

    users = mydb.users.find().sort("time_stamp", -1).skip((page_no - 1) * batch_size).limit(batch_size)
    result = []
    for user in users:
        result.append(user)
    return jsonify({"count": get_users_count(), "users": result})

@app.route('/search_movies')
def search_movies():
    search_string = ""
    print "hello"
    if request.args and request.args.get("s"):
        search_string = request.args.get("s")
        result = omdb.search_movie(search_string)
        response = []
        for movie in result:
            try:
                print movie.title
                movie["_id"] = movie["imdb_id"]
                if movie["poster"].endswith(".jpg"):
                    response.append(movie)
                    alreadyExists = mydb.movies.find({"_id" : movie["imdb_id"]})

                    if count_iterable(alreadyExists) > 0:
                        movie.stored = "true";
                    else:
                        movie.stored = "false";

            except Exception:
                pass
    return jsonify(response)


# Helpers

def count_iterable(i):
    return sum(1 for e in i)

def get_users_count():
    return user_count;

def get_movies_count():
    return count;

def calculate_movies_count():
    global count;
    count = math.ceil(mydb.movies.count() / float(batch_size));
    print count;

def calculate_users_count():
    global user_count;
    user_count = math.ceil(mydb.users.count() / float(batch_size));
    print user_count;

def computeMD5hash(string):
    m = hashlib.md5()
    m.update(string.encode('utf-8'))
    return m.hexdigest()

@app.route('/upload', methods=['GET','POST'])
def upload():
    if request.method == 'POST' and 'photo' in request.files:
        filename = photos.save(request.files['photo'])
        return jsonify({"message" : "success", "url" : photos.url(filename)})
    else:
        return jsonify({"message" : "invalid"})
@app.route('/activities', methods=['GET'])
def get_activites():
    username = None
    if request.args:
        username = request.args("username", None)
    result = []
    if username:
        activity_iter = mydb.activity.find({"user_id" : username}).sort("time_stamp",-1).limit(20);
        for activity in activity_iter:
            result.append(activity)
    else:
        activity_iter = mydb.activity.find().sort("time_stamp",-1).limit(20);
        for activity in activity_iter:
            activity["_id"] = "[HIDDEN]"
            result.append(activity)
    return jsonify({"activities" : result})

# Main
def isInArray(source, target, id1, id2):
    for sourceItem in source:
        if(sourceItem.get(id1) == target.get(id2)):
            return sourceItem
    else:
        return False

def createActivity(userImage, username, verb,moviename, rating):
    mydb.activity.insert_one({
        "profile_url" : userImage,
        "username" : username,
        "verb" : verb,
        "moviename" : moviename,
        "rating" : rating,
        "time_stamp" : datetime.datetime.now().isoformat()
    })
if __name__ == '__main__':
    init_user_rating_matrix()
    app.run(debug=True)


def isInArray(source, target, id1, id2):
    print target
    for sourceItem in source:
        print sourceItem
        if(sourceItem.get(id1) == target.get(id2)):
            return sourceItem
    else:
        return False
