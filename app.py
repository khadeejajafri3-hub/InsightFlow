import os
import uuid
import threading
import json
from flask import Flask, render_template, request, send_from_directory, jsonify, url_for
from werkzeug.utils import secure_filename
from generator import VideoReportGenerator

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_VIDEOS'] = os.path.join('static', 'videos')
app.config['SECRET_KEY'] = 'video-gen-secret-key'

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['STATIC_VIDEOS'], exist_ok=True)

ALLOWED_EXTENSIONS_CSV = {'csv'}
ALLOWED_EXTENSIONS_MUSIC = {'mp3', 'wav'}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

# Persistent Job Store
JOBS_FILE = 'jobs.json'

def load_jobs():
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_jobs(jobs_data):
    with open(JOBS_FILE, 'w') as f:
        json.dump(jobs_data, f)

jobs = load_jobs()

def update_job_status(job_id, status, video_url=None, error=None):
    jobs = load_jobs()
    jobs[job_id] = jobs.get(job_id, {})
    jobs[job_id]['status'] = status
    if video_url: jobs[job_id]['video_url'] = video_url
    if error: jobs[job_id]['error'] = error
    save_jobs(jobs)

def generate_video_job(job_id, csv_path, music_path, theme, narrate, lang, report_title):
    with app.app_context():
        try:
            update_job_status(job_id, 'processing')
            generator = VideoReportGenerator(theme=theme)
            
            output_filename = f"report_{job_id}.mp4"
            output_path = os.path.join(app.config['STATIC_VIDEOS'], output_filename)
            
            final_path = generator.generate_report(
                config={'sections': [], 'title': report_title}, 
                output_file=output_path,
                csv_path=csv_path,
                music_file=music_path,
                music_volume=0.15,
                narrate=narrate,
                narration_lang=lang
            )
            
            final_filename = os.path.basename(final_path)
            update_job_status(job_id, 'completed', video_url=f"/static/videos/{final_filename}")
        except Exception as e:
            print(f"Error generating video: {e}")
            update_job_status(job_id, 'failed', error=str(e))

@app.route('/')
def home():
    return render_template('home.html')
@app.route('/upload')
def upload():
    return render_template('upload.html')

@app.route('/generate', methods=['POST'])
def generate():
    csv_file = request.files.get('csv_file')
    music_file = request.files.get('music_file')
    report_title = request.form.get('report_title', 'Analytics Report')
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

    update_job_status(job_id, 'queued')
    
    # Run generation in background thread
    thread = threading.Thread(target=generate_video_job, args=(job_id, csv_path, music_path, theme, narrate, lang, report_title))
    thread.start()

    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def status(job_id):
    current_jobs = load_jobs()
    job = current_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
