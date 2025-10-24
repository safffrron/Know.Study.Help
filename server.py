# import necessary modules
# for resource upload - work with files
import os
import sqlite3 
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, g, flash
from werkzeug.utils import secure_filename


# folder for uploaded files
# config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'group_resources.db')

# initialize Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # temporary secret key for session management
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# allowed file types
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'pptx', 'txt'}

GROUP_NAME = "Compilers" # temporary group name
uploader = "Demo User" # temporary uploader name
# DB helpers
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row  # enable dict-like access: row['id']
    return db

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploader TEXT,
            timestamp TEXT NOT NULL,
            group_name TEXT
        );
    ''')
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def insert_resource(filename, filepath, uploader, group_name=None):
    db = get_db()
    timestamp = datetime.utcnow().isoformat()  # UTC ISO timestamp
    db.execute(
        'INSERT INTO resources (filename, filepath, uploader, timestamp, group_name) VALUES (?, ?, ?, ?, ?)',
        (filename, filepath, uploader, timestamp, group_name)
    )
    db.commit()

def fetch_resources_for_group(group_name=None):
    db = get_db()
    if group_name:
        cur = db.execute('SELECT * FROM resources WHERE group_name = ? ORDER BY id DESC', (group_name,))
    else:
        cur = db.execute('SELECT * FROM resources ORDER BY id DESC')
    return cur.fetchall()

# temp data for the group
# group_data = {
#     'name': 'Compilers',
#     'description': 'A group for compiler enthusiasts',
#     'members': ['Hari', 'Adarsh', 'Sneha'],
#     'resources': [
#         {"title": "Compiler Design Basics", "link": "http://example.com/compiler-basics"},
#         {"title": "Advanced Compiler Techniques", "link": "http://example.com/advanced-compiler"}
#     ]
# }

# routes
@app.route('/', methods=['GET', 'POST'])
def group_page():
    
    # initialize db on first request if needed
    init_db()
    
    if request.method == 'POST':
        # handle file upload
        if 'file' not in request.files:
            return redirect(request.url)       # "No file part"
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)       # "No selected file"
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # save to group-specific folder optionally later; for now store in uploads/
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # If filename conflict, append timestamp to filename to avoid overwriting
            if os.path.exists(save_path):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            file.save(save_path)

            # save metadata in DB
            # insert_resource(filename=filename,
            #                 filepath=save_path,
            #                 uploader=uploader,
            #                 group_name=GROUP_NAME)

            insert_resource(filename=filename,
                filepath=save_path,
                uploader=uploader,
                group_name=GROUP_NAME)

            return redirect(url_for('group_page'))

    # GET -> fetch resources from DB
    resources = fetch_resources_for_group(GROUP_NAME)
    # map rows to simple dicts for template convenience
    resources_list = [
        {
            'id': r['id'],
            'title': r['filename'],
            'link': url_for('uploaded_file', filename=r['filename']),
            'uploader': r['uploader'],
            'timestamp': r['timestamp'].replace("T", " ")[:19]
        } for r in resources
    ]

    group_data = {
    'name': 'Compilers',
    'description': 'A group for compiler enthusiasts',
    'members': ['Hari', 'Adarsh', 'Sneha'],
    'resources': resources_list
    # [
    #     {"title": "Compiler Design Basics", "link": "http://example.com/compiler-basics"},
    #     {"title": "Advanced Compiler Techniques", "link": "http://example.com/advanced-compiler"}
    # ]
}

        #     filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        #     file.save(filepath)
        #     group_data["resources"].append({
        #         "title": file.filename,
        #         "link": url_for('uploaded_file', filename=file.filename)
        #     })
        #     return redirect(url_for('group_page'))
        #     # return f"File {file.filename} uploaded successfully"
        # else:
        #     return "File type not allowed"
    return render_template('group.html', group=group_data)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/delete/<int:resource_id>', methods=['POST'])
def delete_resource(resource_id):
    db = get_db()
    # Fetch file path first
    cur = db.execute('SELECT filepath FROM resources WHERE id = ?', (resource_id,))
    row = cur.fetchone()
    if row:
        filepath = row[0]
        # Remove DB entry
        db.execute('DELETE FROM resources WHERE id = ?', (resource_id,))
        db.commit()
        # Remove actual file
        if os.path.exists(filepath):
            os.remove(filepath)
        flash('Resource deleted successfully!')
    else:
        flash('Resource not found!')
    return redirect(url_for('group_page'))

if __name__== "__main__":
    app.run(debug=True)