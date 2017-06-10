var request = require('request');
var express        =        require("express");
var bodyParser     =        require("body-parser");
var app            =        express();
//Here we are configuring express to use body-parser as middle-ware.
app.get('*', function(req,res) {
  console.log("got " + req.url)
  //modify the url in any way you want
  console.log(req.body)
  var newurl = 'http://localhost:5000' + req.url;
  req.pipe(request(newurl)).pipe(res);
});
app.post('*', (req, res) => {
  console.log(req)
  var newurl = 'http://localhost:5000' + req.url
  req.pipe(request.post(newurl, { json: true, body: req.body }), { end: false }).pipe(res);
})
app.use(bodyParser.urlencoded({ extended: false }));
app.use(bodyParser.json());

app.listen(8080, function(){
    console.log('Listening!');
});
