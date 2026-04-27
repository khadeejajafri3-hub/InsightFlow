import os
import uuid
import threading
from flask import Flask, render_template, request, send_from_directory, jsonify, url_for, redirect, flash
from werkzeug.utils import secure_filename
from generator import VideoReportGenerator

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_VIDEOS'] = os.path.join('static', 'videos')
app.config['SECRET_KEY'] = 'video-gen-secret-key'
app.config['SERVER_NAME'] = 'localhost:5000'
app.config['APPLICATION_ROOT'] = '/'
app.config['PREFERRED_URL_SCHEME'] = 'http'

# Simple in-memory user store for signup/login
users = {}

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['STATIC_VIDEOS'], exist_ok=True)

ALLOWED_EXTENSIONS_CSV = {'csv'}
ALLOWED_EXTENSIONS_MUSIC = {'mp3', 'wav'}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

# Dictionary to store job status
jobs = {}

def generate_video_job(job_id, csv_path, music_path, theme, narrate, lang):
    try:
        jobs[job_id]['status'] = 'processing'
        generator = VideoReportGenerator(theme=theme)
        
        output_filename = f"report_{job_id}.mp4"
        output_path = os.path.join(app.config['STATIC_VIDEOS'], output_filename)
        
        # We need a base config or it will use the default sample data logic in generator.py
        # Actually, VideoReportGenerator.generate_report handles csv_path and generates insights.
        # We can pass an empty config if we provide csv_path.
        
        final_path = generator.generate_report(
            config={'sections': []}, # Will be populated if csv_path is provided
            output_file=output_path,
            csv_path=csv_path,
            music_file=music_path,
            music_volume=0.15,
            narrate=narrate,
            narration_lang=lang
        )
        
        jobs[job_id]['status'] = 'completed'
        with app.app_context():
            jobs[job_id]['video_url'] = url_for('static', filename=f'videos/{output_filename}')
    except Exception as e:
        print(f"Error generating video: {e}")
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload')
def upload():
    return render_template('upload.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email')
        password = request.form.get('password')

        if action == 'signup':
            confirm_password = request.form.get('cpass')
            if password != confirm_password:
                flash('Passwords do not match. Please try again.', 'error')
                return redirect(url_for('register', show='signup'))
            if email in users:
                flash('User already exists. Please login.', 'error')
                return redirect(url_for('register', show='login'))
            users[email] = password
            flash('Signup successful! Please login to continue.', 'success')
            return redirect(url_for('register', show='login'))

        if action == 'login':
            stored_password = users.get(email)
            if stored_password and stored_password == password:
                flash('Login successful! Redirecting to home...', 'success')
                return redirect(url_for('home'))
            flash('Invalid email or password. Please try again.', 'error')
            return redirect(url_for('register', show='login'))

    return render_template('register.html')

@app.route('/login')
def login():
    return redirect(url_for('register', show='login'))

@app.route('/generate', methods=['POST'])
def generate():
    csv_file = request.files.get('csv_file')
    music_file = request.files.get('music_file')
    theme = request.form.get('theme', 'vibrant')
    narrate = request.form.get('narrate') == 'on'
    lang = request.form.get('lang', 'en')

    if not csv_file or csv_file.filename == '':
        return jsonify({'error': 'No CSV file uploaded'}), 400

    if not allowed_file(csv_file.filename, ALLOWED_EXTENSIONS_CSV):
        return jsonify({'error': 'Invalid CSV file format'}), 400

    job_id = str(uuid.uuid4())
    csv_filename = secure_filename(f"{job_id}_{csv_file.filename}")
    csv_path = os.path.join(app.config['UPLOAD_FOLDER'], csv_filename)
    csv_file.save(csv_path)

    music_path = None
    if music_file and music_file.filename:
        filename = music_file.filename
        if allowed_file(filename, ALLOWED_EXTENSIONS_MUSIC):
            music_filename = secure_filename(f"{job_id}_{filename}")
            music_path = os.path.join(app.config['UPLOAD_FOLDER'], music_filename)
            music_file.save(music_path)

    jobs[job_id] = {'status': 'queued'}
    
    # Run generation in background thread
    thread = threading.Thread(target=generate_video_job, args=(job_id, csv_path, music_path, theme, narrate, lang))
    thread.start()

    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
