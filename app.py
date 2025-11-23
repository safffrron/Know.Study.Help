
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import secrets
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scraper import CourseraScraper

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
course_scraper = CourseraScraper()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    created_groups = db.relationship('Group', backref='creator', lazy=True)
    messages = db.relationship('Message', backref='author', lazy=True)
    uploaded_files = db.relationship('Resource', backref='uploader', lazy=True)

# group_members = db.Table('group_members',
#     db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
#     db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True)
# )

# class Group(db.Model):
#     __tablename__ = 'groups'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     description = db.Column(db.Text, nullable=True)
#     creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
#     # Relationships
#     members = db.relationship('User', secondary=group_members, backref='groups')
#     messages = db.relationship('Message', backref='group', lazy=True, cascade='all, delete-orphan')
#     resources = db.relationship('Resource', backref='group', lazy=True, cascade='all, delete-orphan')
#     polls = db.relationship('Poll', backref='group', lazy=True, cascade='all, delete-orphan')
#     join_requests = db.relationship('JoinRequest', backref='group', lazy=True, cascade='all, delete-orphan')
# ============= LOGIN MANAGER =============

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============= COURSE SCRAPER (MOCK) =============

def search_courses(query, limit=6):
    """
    Fetch live courses from Coursera using the scraper.
    Returns a list of course dictionaries or empty list on failure.
    """
    try:
        courses = course_scraper.scrape_courses(query, limit=limit)
        return courses or []
    except Exception as exc:
        app.logger.error("Course scraping failed for query '%s': %s", query, exc)
        return []
    


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

        # Demo credentials (replace with actual authentication)
        # if username == 'admin' and password == 'password':
        #     session['user'] = username
        #     success = 'Login successful!'
        #     return redirect(url_for('dashboard'))
        # else:
        #     error = 'Invalid username or password'
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
