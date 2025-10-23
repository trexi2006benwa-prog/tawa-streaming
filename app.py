import os
import boto3
from flask import Flask, render_template, request, jsonify
import sqlite3
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

app = Flask(__name__)

# AWS S3 Configuration
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME', 'tawa-streaming')
AWS_REGION = 'af-south-1'  # Cape Town region

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION
)

# Initialize database
def init_db():
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         title TEXT NOT NULL,
         filename TEXT NOT NULL,
         s3_key TEXT NOT NULL,
         upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

def allowed_file(filename):
    allowed_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

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
            s3_key = f"videos/{filename}"
            
            # Upload to S3
            try:
                s3_client.upload_fileobj(
                    file,
                    AWS_BUCKET_NAME,
                    s3_key,
                    ExtraArgs={'ACL': 'public-read', 'ContentType': 'video/mp4'}
                )
            except ClientError as e:
                return jsonify({'error': f'S3 upload failed: {str(e)}'}), 500
            
            # Save to database
            conn = sqlite3.connect('tawa.db')
            c = conn.cursor()
            c.execute("INSERT INTO videos (title, filename, s3_key) VALUES (?, ?, ?)", 
                     (title, filename, s3_key))
            conn.commit()
            conn.close()
            
            # Generate the S3 URL for the response
            s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
            
            return jsonify({
                'message': 'Video uploaded successfully to cloud!', 
                'filename': filename,
                's3_url': s3_url
            })
        else:
            return jsonify({'error': 'File type not allowed. Please use MP4, AVI, MOV, MKV, or WEBM.'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/videos')
def get_videos():
    try:
        conn = sqlite3.connect('tawa.db')
        c = conn.cursor()
        c.execute("SELECT id, title, filename, s3_key, upload_date FROM videos ORDER BY upload_date DESC")
        videos = c.fetchall()
        conn.close()
        
        video_list = []
        for video in videos:
            # Generate S3 URL for each video
            s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video[3]}"  # s3_key is at index 3
            
            video_list.append({
                'id': video[0],        # id
                'title': video[1],     # title
                'filename': video[2],  # filename
                's3_url': s3_url,      # generated URL
                'upload_date': video[4] # upload_date at index 4 (this was the bug!)
            })
        
        return jsonify(video_list)
    
    except Exception as e:
        print(f"Error in /videos: {e}")
        return jsonify([])  # Return empty array instead of crashing

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

