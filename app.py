"""
Flask Course Search and Collaboration App
Main application file
"""

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

# ============= DATABASE MODELS =============


# Association table for group members (many-to-many)
group_members = db.Table('group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
     # Relationships
    created_groups = db.relationship('Group', backref='creator', lazy=True)

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    #Relationships
    members = db.relationship('User', secondary=group_members, backref='groups')
    join_requests = db.relationship('JoinRequest', backref='group', lazy=True, cascade='all, delete-orphan')


class JoinRequest(db.Model):
    __tablename__ = 'join_requests'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)

    user = db.relationship('User', backref='join_requests')

#Login Module

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


# ============= ROUTES =============

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

@app.route('/dashboard')
@login_required
def dashboard():
    groups = Group.query.all()
    my_group_ids = {group.id for group in current_user.groups}
    joined_groups = [group for group in groups if group.id in my_group_ids]
    other_groups = [group for group in groups if group.id not in my_group_ids]
    user_requests = JoinRequest.query.filter_by(user_id=current_user.id)\
        .order_by(JoinRequest.created_at.desc()).all()
    join_request_statuses = {}
    for join_request in user_requests:
        if join_request.group_id not in join_request_statuses:
            join_request_statuses[join_request.group_id] = join_request.status
    return render_template(
        'dashboard.html',
        groups=other_groups,
        joined_groups=joined_groups,
        my_group_ids=my_group_ids,
        join_request_statuses=join_request_statuses
    )

@app.route('/search', methods=['POST'])
@login_required
def search():
    query = request.form.get('query', '')
    if query:
        courses = search_courses(query)
        if courses:
            return jsonify({'courses': courses})
        return jsonify({'courses': [], 'message': 'No courses found or scraping failed'}), 200
    return jsonify({'courses': [], 'message': 'Query required'}), 400

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Group name is required', 'error')
        return redirect(url_for('dashboard'))
    
    # Create new group
    new_group = Group(
        name=name,
        description=description,
        creator_id=current_user.id
    )
    db.session.add(new_group)
    db.session.commit()
    
    # Add creator as first member
    new_group.members.append(current_user)
    db.session.commit()
    
    flash('Group created successfully!', 'success')
    return redirect(url_for('group_page', group_id=new_group.id))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    group_id = request.form.get('group_id')
    message = request.form.get('message', '').strip()
    
    group = Group.query.get(group_id)
    
    if not group:
        flash('Group not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if already a member
    if current_user in group.members:
        flash('You are already a member of this group.', 'info')
        return redirect(url_for('group_page', group_id=group.id))
    
    existing_request = JoinRequest.query.filter_by(
        group_id=group.id,
        user_id=current_user.id
    ).order_by(JoinRequest.created_at.desc()).first()
    
    if existing_request and existing_request.status == 'pending':
        flash('You already have a pending request for this group.', 'info')
        return redirect(url_for('dashboard'))
    
    if existing_request and existing_request.status in ('approved', 'rejected'):
        existing_request.status = 'pending'
        existing_request.message = message
        existing_request.created_at = datetime.utcnow()
        existing_request.responded_at = None
        join_request = existing_request
    else:
        join_request = JoinRequest(
            user_id=current_user.id,
            group_id=group.id,
            message=message
        )
        db.session.add(join_request)
    
    db.session.commit()
    
    flash('Join request sent to the group creator.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/group/<int:group_id>')
@login_required
def group_page(group_id):
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member
    if current_user not in group.members:
        flash('You are not a member of this group', 'error')
        return redirect(url_for('dashboard'))
    
    messages = Message.query.filter_by(group_id=group_id).order_by(Message.timestamp.asc()).all()
    resources = Resource.query.filter_by(group_id=group_id).order_by(Resource.uploaded_at.desc()).all()
    ongoing_polls = Poll.query.filter_by(group_id=group_id, is_closed=False).order_by(Poll.created_at.desc()).all()
    finished_polls = Poll.query.filter_by(group_id=group_id, is_closed=True).order_by(Poll.closed_at.desc()).all()
    
    should_open_polls = request.args.get('polls') == 'open'
    pending_requests = []
    if current_user.id == group.creator_id:
        pending_requests = JoinRequest.query.filter_by(
            group_id=group_id,
            status='pending'
        ).order_by(JoinRequest.created_at.asc()).all()

    return render_template(
        'group.html',
        group=group,
        messages=messages,
        resources=resources,
        ongoing_polls=ongoing_polls,
        finished_polls=finished_polls,
        should_open_polls=should_open_polls,
        pending_requests=pending_requests
    )


# ============= DATABASE INITIALIZATION =============

def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully!")

# ============= RUN APP =============

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)