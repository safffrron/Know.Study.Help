from flask import Flask, render_template

app = Flask(__name__)

posts = [
    {
        'author' : 'J.K Rowling',
        'Book' : 'Harry Potter: Philospher\'s Stone',
        'Year' : '1991'
    },
    {
        'author' : 'Rick Riordian',
        'Book' : 'Percy Jackson: Lightning Thief',
        'Year' : '2002'
    }
]

@app.route('/')
@app.route('/home')
def home():
    #return templates are used with return statement, to render the page (passed as arg.) on browser
    return render_template("index.html")
    #return 'Hello, Himadri!'


@app.route('/about')
@app.route('/about-me')
def about():
    return 'About Page!'


@app.route('/experiment')
def experiment():
    return render_template("experiment.html", posts=posts)

if __name__ == "__main__":
    app.run(debug=True, port=8000)