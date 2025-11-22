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

#
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