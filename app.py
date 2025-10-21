from flask import Flask, render_template, request, jsonify, send_file
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)

# TAWA Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'avi', 'mov', 'mkv'}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
def init_db():
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         title TEXT NOT NULL,
         filename TEXT NOT NULL,
         upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file'}), 400
        
        file = request.files['video']
        title = request.form.get('title', 'Untitled')
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Save to database
            conn = sqlite3.connect('tawa.db')
            c = conn.cursor()
            c.execute("INSERT INTO videos (title, filename) VALUES (?, ?)", 
                     (title, filename))
            conn.commit()
            conn.close()
            
            return jsonify({'message': 'Video uploaded successfully!', 'filename': filename})
        else:
            return jsonify({'error': 'File type not allowed'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/video/<filename>')
def stream_video(filename):
    try:
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        return send_file(video_path)
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/videos')
def get_videos():
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    c.execute("SELECT * FROM videos")
    videos = c.fetchall()
    conn.close()
    
    video_list = []
    for video in videos:
        video_list.append({
            'id': video[0],
            'title': video[1],
            'filename': video[2],
            'upload_date': video[3]
        })
    
    return jsonify(video_list)
    
    if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))  # Render uses port 10000
    print("🎬 TAWA Streaming Platform Starting...")
    print("📁 Upload folder ready")
    print("💾 Database initialized")
    print("🌐 Server running!")

    app.run(host='0.0.0.0', port=port)
