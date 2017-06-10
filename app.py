from flask import Flask, jsonify, request, send_from_directory
import omdb;
from pymongo import MongoClient
import math;
import datetime
import hashlib
from flask_uploads import (UploadSet, configure_uploads, IMAGES,
                              UploadNotAllowed)
from sklearn.cluster import KMeans
import numpy as np
import sys
import pyfpgrowth
# App

UPLOADED_PHOTOS_DEST = '/tmp/photolog'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__, static_url_path='')


# Global Vars
omdb.api._client.params_map['apikey'] = 'apikey'
omdb.set_default('apikey', '26029d08')
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
transactions = []
genres = []
lastCall = 0;
recommendation = {
    "predicted_numpy_matrix" : np.array(user_rating_matrix)
}


def init_user_rating_matrix():
    user_rating_cursor = mydb.user_ratings.find()

    for user_rating_item in user_rating_cursor:
        insert_into_matrix(user_rating_item.get("user_id"), user_rating_item.get("movie_id"), user_rating_item.get("rating"))
    print "[info] Loading initial user matrix complete"

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

def matrix_factorization(R, P, Q, K, steps=5000, alpha=0.0002, beta=0.02):
    Q = Q.T
    for step in xrange(steps):
        for i in xrange(len(R)):
            for j in xrange(len(R[i])):
                if R[i][j] > 0:
                    eij = R[i][j] - np.dot(P[i,:],Q[:,j])
                    for k in xrange(K):
                        P[i][k] = P[i][k] + alpha * (2 * eij * Q[k][j] - beta * P[i][k])
                        Q[k][j] = Q[k][j] + alpha * (2 * eij * P[i][k] - beta * Q[k][j])
        eR = np.dot(P,Q)
        e = 0
        for i in xrange(len(R)):
            for j in xrange(len(R[i])):
                if R[i][j] > 0:
                    e = e + pow(R[i][j] - np.dot(P[i,:],Q[:,j]), 2)
                    for k in xrange(K):
                        e = e + (beta/2) * (pow(P[i][k],2) + pow(Q[k][j],2))
        if e < 0.001:
            break
    return P, Q.T
def predict_numpy_matrix():
    print "[info] Predictng numpy matrix"

    R = convert_to_numpy(user_rating_matrix)
    N = len(R)
    M = len(R[0])
    K = 5
    P = np.random.rand(N,K)
    Q = np.random.rand(M,K)
    nP, nQ = matrix_factorization(R, P, Q, K)
    nR = np.dot(nP, nQ.T)
    nR = np.around(nR, decimals = 3)
    recommendation["predicted_numpy_matrix"] = nR
    print "[Done] Predictng numpy matrix"

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
    print "I do came here.."
    content = request.get_json(force=True)
    print request
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
    global lastCall
    lastCall += 1
    i = get_item_index(id, user_index_dict)
    if i >= len(user_rating_matrix):
        return jsonify({"movies":[], "message" : "Insufficient movies"})
    print str(i) + " <<>> " + str(len(recommendation["predicted_numpy_matrix"]) )

    print str(lastCall) + " <<LastCall>> "
    if(lastCall % 10 == 0 or i >= len(recommendation["predicted_numpy_matrix"])):
        print "Re Calculating"
        predict_numpy_matrix()
    else:
        print "Re Using"
    nR = recommendation["predicted_numpy_matrix"]

    a = nR[i].tolist()
    max_i =  np.argsort(a)[::-1]
    result = []
    max_i = max_i.tolist()
    total_movies = 0
    for index in max_i:
        if total_movies > 5:
            break
        if user_rating_matrix[i][index] == 0:

            if a[index] > 2.5:
                total_movies = total_movies + 1
                movie_id = key_from_value(index, movie_index_dict)
                movie = mydb.movies.find_one({"_id" : movie_id})
                if a[index] > 5:
                    movie["predicted_rating"] = 5
                else:
                    movie["predicted_rating"] = a[index]
                result.append(movie)

    return jsonify({"movies" : result})
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

@app.route('/fpRecommender/<string:id>')
def getFPRecommendations(id):
    enrichedRecList = []
    minsup = 3
    if request.args and request.args.get("minsup"):
        minsup = request.args.get("minsup")

    recommendations = fpRecommender(id, int(minsup))
    movies_sample = []
    for recommendation in recommendations:
        enrichedRec = []
        for movie in recommendation.get("reason", []):
            enrichedRec.append(mydb.movies.find_one({"_id" : movie})["title"])
        if(len(enrichedRec) > 1):
            enrichedRecList.append({
                "reason" : enrichedRec,
                "movies" : recommendation.get("movies", [])
            })
        movies_sample = concatWithoutDuplicates(movies_sample, recommendation.get("movies", []))
    print movies_sample
    enrichedMoviesSample = []
    for movie in movies_sample:
        enrichedMoviesSample.append(mydb.movies.find_one({"_id" : movie}))
    labels =  formClusters(n_cl = 2, movies = enrichedMoviesSample).labels_
    return jsonify({"recommendation" : enrichedRecList, "movie_sample" : enrichedMoviesSample, "labels" : labels.tolist()})

@app.route('/similar/<string:id>')
def getSimilar(id):
    movies_c = mydb.movies.find();
    movie_sample = []
    index = 0;
    i = 0;
    for movie in movies_c:
        if movie["_id"] == id:
            index = i
            print "selected index " + str(index)
        i += 1
        movie_sample.append(movie)

    print i;
    n_c = i/5;
    print n_c
    labels = formClusters(n_cl = n_c, movies = movie_sample).labels_
    print labels
    class_m = labels[index]
    result = []
    i = 0
    for l in labels:
        if l == class_m and index != i:
            result.append(movie_sample[i])
        i += 1

    return jsonify(result)

def concatWithoutDuplicates(list1, list2):
    return list1 + list(set(list2) - set(list1))

def updateTransactions(minsup):
    transactions = []
    users = mydb.users.find();
    for user in users:
        movie_id_list = [];
        ratings = mydb.user_ratings.find({"user_id" : user.get("_id"), "rating" : {"$gt" : 2.9}})
        for rating in ratings:
            movie_id_list.append(rating.get("movie_id"))
        if(len(movie_id_list) > 0):
            transactions.append(movie_id_list)
    size = 0;
    itemsets = pyfpgrowth.find_frequent_patterns(transactions, minsup)
    patterns = []
    for itemset in itemsets:
        if(len(itemset) > 1):
            patterns.append(itemset)

    return patterns


def intersect(a, b):
    return list(set(a) & set(b))

def difference(a,b):
    return list(set(a).symmetric_difference(set(b)))

def fpRecommender(user_id, minsup):
    ratings = mydb.user_ratings.find({"user_id" : user_id, "rating" : {"$gt" : 2.9}})
    user_movies = []
    recommended_movies = []
    for rating in ratings:
        user_movies.append(rating.get("movie_id"))
    patterns = updateTransactions(minsup)
    for pattern in patterns:
        intersection = intersect(user_movies, pattern)
        if(len(intersection) > 0 and len(intersection) < len(pattern)):

            print float(len(intersection))/len(pattern)
            if(float(len(intersection))/len(pattern) > 0.4):
                diff = difference(pattern, intersection)
                recommendation = {
                    "reason" : intersection,
                    "movies" : diff
                }
                recommended_movies.append(recommendation)
    return recommended_movies




@app.route('/movie/<string:id>')
def get_movie(id):
    movie = mydb.movies.find_one({"_id" : id})
    return jsonify(movie)
@app.route('/search_movies')
def search_movies():
    search_string = ""
    response = []
    print "hello"
    if request.args and request.args.get("s"):
        search_string = request.args.get("s")
        auto_store = request.args.get("auto_store")

        result = omdb.search_movie(search_string)

        for movie in result:
            try:
                print movie.title
                movie["_id"] = movie["imdb_id"]
                if movie["poster"].endswith(".jpg"):
                    response.append(movie)
                    alreadyExists = mydb.movies.find({"_id" : movie["imdb_id"]})
                    alreadyExists = count_iterable(alreadyExists) > 0
                    if(not alreadyExists and auto_store == "1"):
                        print "going to save a movie " + movie["_id"]
                        movieInfo = omdb.imdbid(movie["_id"])
                        movieInfo["_id"] = movieInfo["imdb_id"]
                        movieInfo["time_stamp"] = datetime.datetime.now().isoformat();
                        mydb.movies.insert_one(movieInfo)
                        print movieInfo.title +" Inserted!"
                        calculate_movies_count();
                    if alreadyExists:
                        movie.stored = "true";
                    else:
                        movie.stored = "false";

            except Exception as e:
                print "Exception has occured"
                print str(e)
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
def transformMovie(movie):
    movie_genre = movie["genre"].split(", ")
    #Sci-Fi, Crime, Mystery, Thriller, Action, Comedy , Adventure, Drama, Horror, Family Short Animation rating, year, runtime
    movie_t = []
    genres = ["Sci-Fi", "Crime", "Thriller", "Action", "Comedy","Adventure","Drama","Horror","Family","Short","Animation"]
    for genre in genres:
        if(genre in movie_genre):
            movie_t.append(1)
        else:
            movie_t.append(0)

    if movie["imdb_rating"] != "N/A":
        movie_t.append(float(movie["imdb_rating"])/ 10)
    else:
        movie_t.append(0)
    movie_t.append(int(movie["year"]) / 2017)
    if movie["runtime"] != "N/A":
        movie_t.append(int(movie["runtime"].split(" ")[0])/ 160)
    else:
        movie_t.append(0)

    return movie_t

def formClusters(n_cl = 2,movies = []):
    movies_a = []
    for movie in movies:
        movies_a.append(transformMovie(movie))

    x = np.array(movies_a)

    kmeans = KMeans(n_clusters=n_cl, random_state=0).fit(x)
    return kmeans


if __name__ == '__main__':
    init_user_rating_matrix()
    #updateTransactions()
    app.run(host='0.0.0.0', debug = True)





def isInArray(source, target, id1, id2):
    print target
    for sourceItem in source:
        print sourceItem
        if(sourceItem.get(id1) == target.get(id2)):
            return sourceItem
    else:
        return False
