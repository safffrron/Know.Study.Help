
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
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join('static', 'charts'), exist_ok=True)

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
    messages = db.relationship('Message', backref='author', lazy=True)
    uploaded_files = db.relationship('Resource', backref='uploader', lazy=True)

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    members = db.relationship('User', secondary=group_members, backref='groups')
    messages = db.relationship('Message', backref='group', lazy=True, cascade='all, delete-orphan')
    resources = db.relationship('Resource', backref='group', lazy=True, cascade='all, delete-orphan')
    polls = db.relationship('Poll', backref='group', lazy=True, cascade='all, delete-orphan')
    join_requests = db.relationship('JoinRequest', backref='group', lazy=True, cascade='all, delete-orphan')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Poll(db.Model):
    __tablename__ = 'polls'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    chart_type = db.Column(db.String(20), default='bar')
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    chart_path = db.Column(db.String(255), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    creator = db.relationship('User', backref='created_polls')
    options = db.relationship('PollOption', backref='poll', cascade='all, delete-orphan')
    votes = db.relationship('PollVote', backref='poll', cascade='all, delete-orphan')

class PollOption(db.Model):
    __tablename__ = 'poll_options'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    votes = db.relationship('PollVote', backref='option', cascade='all, delete-orphan')

class PollVote(db.Model):
    __tablename__ = 'poll_votes'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('poll_options.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)

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

# ============= LOGIN MANAGER =============

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============= COURSE SCRAPER =============

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

def generate_poll_chart(poll):
    options = poll.options
    if not options:
        return

    labels = [opt.text for opt in options]
    counts = [len(opt.votes) for opt in options]
    total_votes = sum(counts)

    if total_votes == 0:
        poll.chart_path = None
        return

    chart_dir = os.path.join('static', 'charts')
    os.makedirs(chart_dir, exist_ok=True)
    filename = f"poll_{poll.id}_{int(datetime.utcnow().timestamp())}.png"
    filepath = os.path.join(chart_dir, filename)

    plt.figure(figsize=(6, 4))
    if poll.chart_type == 'pie':
        plt.pie(counts, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.axis('equal')
    else:
        plt.bar(labels, counts, color='#4a90e2')
        plt.ylabel('Votes')
        plt.xticks(rotation=15, ha='right')
    plt.title(poll.question)
    plt.tight_layout()
    plt.savefig(filepath, transparent=True)
    plt.close()

    poll.chart_path = f'charts/{filename}'

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

        # Demo credentials 
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


@app.route('/group/<int:group_id>/send_message', methods=['POST'])
@login_required
def send_message(group_id):
    group = Group.query.get_or_404(group_id)
    
    if current_user not in group.members:
        return jsonify({'error': 'Unauthorized'}), 403
    
    content = request.form.get('content')
    
    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    message = Message(
        content=content,
        user_id=current_user.id,
        group_id=group_id
    )
    db.session.add(message)
    db.session.commit()
    
    return jsonify({
        'id': message.id,
        'content': message.content,
        'author': message.author.username,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/group/<int:group_id>/upload', methods=['POST'])
@login_required
def upload_resource(group_id):
    group = Group.query.get_or_404(group_id)
    
    if current_user not in group.members:
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard'))
    
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('group_page', group_id=group_id))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('group_page', group_id=group_id))
    
    if file:
        original_filename = secure_filename(file.filename)
        filename = f"{secrets.token_hex(8)}_{original_filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        resource = Resource(
            filename=filename,
            original_filename=original_filename,
            user_id=current_user.id,
            group_id=group_id
        )
        db.session.add(resource)
        db.session.commit()
        
        flash('File uploaded successfully!', 'success')
    
    return redirect(url_for('group_page', group_id=group_id))

@app.route('/download/<int:resource_id>')
@login_required
def download_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    
    if current_user not in resource.group.members:
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard'))
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], resource.filename, 
                             as_attachment=True, download_name=resource.original_filename)

@app.route('/delete_resource/<int:resource_id>', methods=['POST'])
@login_required
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    
    # Only uploader or group creator can delete
    if current_user.id != resource.user_id and current_user.id != resource.group.creator_id:
        flash('Unauthorized', 'error')
        return redirect(url_for('group_page', group_id=resource.group_id))
    
    # Delete file from filesystem
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], resource.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    
    group_id = resource.group_id
    db.session.delete(resource)
    db.session.commit()
    
    flash('Resource deleted successfully!', 'success')
    return redirect(url_for('group_page', group_id=group_id))

@app.route('/group/<int:group_id>/messages')
@login_required
def get_messages(group_id):
    group = Group.query.get_or_404(group_id)
    
    if current_user not in group.members:
        return jsonify({'error': 'Unauthorized'}), 403
    
    messages = Message.query.filter_by(group_id=group_id).order_by(Message.timestamp.asc()).all()
    
    return jsonify({
        'messages': [{
            'id': msg.id,
            'content': msg.content,
            'author': msg.author.username,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for msg in messages]
    })

@app.route('/group/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        flash('You are not a member of this group.', 'error')
        return redirect(url_for('dashboard'))

    # Prevent leaving if user is the only member
    if len(group.members) == 1:
        flash('You are the only member. Delete the group instead.', 'error')
        return redirect(url_for('group_page', group_id=group.id))

    group.members.remove(current_user)
    db.session.commit()

    flash(f'You left {group.name}.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/join_requests/<int:request_id>/approve', methods=['POST'])
@login_required
def approve_join_request(request_id):
    join_request = JoinRequest.query.get_or_404(request_id)
    group = join_request.group

    if current_user.id != group.creator_id:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('dashboard'))

    if join_request.status != 'pending':
        flash('This request has already been processed.', 'info')
        return redirect(url_for('group_page', group_id=group.id))

    join_request.status = 'approved'
    join_request.responded_at = datetime.utcnow()

    if join_request.user not in group.members:
        group.members.append(join_request.user)

    db.session.commit()

    flash(f"{join_request.user.username} has been added to {group.name}.", 'success')
    return redirect(url_for('group_page', group_id=group.id))

@app.route('/join_requests/<int:request_id>/reject', methods=['POST'])
@login_required
def reject_join_request(request_id):
    join_request = JoinRequest.query.get_or_404(request_id)
    group = join_request.group

    if current_user.id != group.creator_id:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('dashboard'))

    if join_request.status != 'pending':
        flash('This request has already been processed.', 'info')
        return redirect(url_for('group_page', group_id=group.id))

    join_request.status = 'rejected'
    join_request.responded_at = datetime.utcnow()

    db.session.commit()

    flash('Join request rejected.', 'info')
    return redirect(url_for('group_page', group_id=group.id))

@app.route('/group/<int:group_id>/polls/create', methods=['POST'])
@login_required
def create_poll(group_id):
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        flash('You must be a group member to create polls.', 'error')
        return redirect(url_for('dashboard'))

    question = request.form.get('poll_question', '').strip()
    chart_type = request.form.get('chart_type', 'bar')
    raw_options = request.form.get('poll_options', '').strip()

    if not question or not raw_options:
        flash('Question and options are required.', 'error')
        return redirect(url_for('group_page', group_id=group_id))

    option_list = [opt.strip() for opt in raw_options.split('\n') if opt.strip()]
    if len(option_list) < 2:
        flash('Provide at least two poll options.', 'error')
        return redirect(url_for('group_page', group_id=group_id))

    poll = Poll(
        question=question,
        chart_type=chart_type if chart_type in ['bar', 'pie'] else 'bar',
        group_id=group_id,
        creator_id=current_user.id
    )
    db.session.add(poll)
    db.session.flush()

    for text in option_list:
        db.session.add(PollOption(text=text, poll_id=poll.id))

    db.session.commit()
    return redirect(url_for('group_page', group_id=group_id, polls='open'))

@app.route('/polls/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    group = poll.group

    if current_user not in group.members:
        flash('You must be a group member to vote.', 'error')
        return redirect(url_for('dashboard'))

    if poll.is_closed:
        flash('This poll is closed.', 'error')
        return redirect(url_for('group_page', group_id=group.id))

    option_id = request.form.get('option_id')
    option = PollOption.query.filter_by(id=option_id, poll_id=poll_id).first()
    if not option:
        flash('Invalid option selected.', 'error')
        return redirect(url_for('group_page', group_id=group.id))

    existing_vote = PollVote.query.filter_by(poll_id=poll_id, user_id=current_user.id).first()
    if existing_vote:
        flash('You already voted in this poll.', 'error')
        return redirect(url_for('group_page', group_id=group.id))

    vote = PollVote(poll_id=poll_id, option_id=option.id, user_id=current_user.id)
    db.session.add(vote)
    db.session.commit()
    return redirect(url_for('group_page', group_id=group.id, polls='open'))

@app.route('/polls/<int:poll_id>/close', methods=['POST'])
@login_required
def close_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    group = poll.group

    if current_user not in group.members:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('dashboard'))

    if current_user.id != poll.creator_id and current_user.id != group.creator_id:
        flash('Only the poll creator or group creator can close the poll.', 'error')
        return redirect(url_for('group_page', group_id=group.id))

    poll.is_closed = True
    poll.closed_at = datetime.utcnow()
    generate_poll_chart(poll)
    db.session.commit()
    return redirect(url_for('group_page', group_id=group.id, polls='open'))

# ============= DATABASE INITIALIZATION =============

def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully!")

# ============= RUN APP =============

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)