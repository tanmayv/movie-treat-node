from pymongo import MongoClient
from sklearn.decomposition import ProjectedGradientNMF
import numpy


client = MongoClient('mongodb://localhost:27017/')
mydb = client['movie_database']


movies = mydb.movies.find()
i = 1
for movie in movies:
    print str(i)+" >> "+movie.get("title") +"--"+ movie.get("_id")
    i = i + 1
users = mydb.users.find()
i = 1
for user in users:
    print str(i) + " >>" + user.get("_id") + "--" + user.get("password")

activities = mydb.activity.find()
i = 1
for activity in activities:
    print str(i) + " >>" + str(activity)

A = numpy.random.uniform(size = [40, 30])
nmf_model = ProjectedGradientNMF(n_components = 5, init='random', random_state=0)
W = nmf_model.fit_transform(A);
H = nmf_model.components_;


print W
print H
