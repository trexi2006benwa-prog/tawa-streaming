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

def fix_database():
    """Add missing columns to existing database"""
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    try:
        # Check if s3_key column exists
        c.execute("PRAGMA table_info(videos)")
        columns = [column[1] for column in c.fetchall()]
        
        if 's3_key' not in columns:
            c.execute("ALTER TABLE videos ADD COLUMN s3_key TEXT")
            print("✅ Added missing s3_key column to existing database")
        else:
            print("✅ s3_key column already exists")
            
    except Exception as e:
        print("Error checking/adding columns:", e)
    finally:
        conn.commit()
        conn.close()

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
    
    # Call the fix function
    fix_database()

def allowed_file(filename):
    allowed_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions
@app.route('/fix-db')
def force_fix_db():
    """Force database fix - run this once then remove the route"""
    fix_database()
    
    # Check if fix worked
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    try:
        c.execute("SELECT id, title, filename, s3_key, upload_date FROM videos LIMIT 1")
        result = "✅ Database fixed successfully! s3_key column exists."
    except Exception as e:
        result = f"❌ Still broken: {e}"
    conn.close()
    
    return result
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
                'upload_date': video[4] # upload_date at index 4
            })
        
        return jsonify(video_list)
    
    except Exception as e:
        print(f"Error in /videos: {e}")
        return jsonify([])  # Return empty array instead of crashing

@app.route('/sitemap.xml')
def sitemap():
    sitemap_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://tawa-streaming.onrender.com/</loc>
    <lastmod>2023-10-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>'''
    return sitemap_xml, 200, {'Content-Type': 'application/xml'}

@app.route('/robots.txt')
def robots():
    robots_txt = '''User-agent: *
Allow: /
Sitemap: https://tawa-streaming.onrender.com/sitemap.xml'''
    return robots_txt, 200, {'Content-Type': 'text/plain'}

# Admin route for private uploads
@app.route('/admin')
def admin_panel():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>TAWA Admin</title>
        <style>
            body { background: #0F172A; color: white; font-family: Arial; padding: 2rem; }
            .admin-form { background: #1E293B; padding: 2rem; border-radius: 10px; max-width: 500px; }
            input, button { padding: 0.8rem; margin: 0.5rem 0; width: 100%; border-radius: 5px; border: 1px solid #334155; }
            button { background: #3B82F6; color: white; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <h1>🎬 TAWA Admin Panel</h1>
        <div class="admin-form">
            <h3>Upload New Video</h3>
            <form id="uploadForm">
                <input type="text" id="videoTitle" placeholder="Video Title" required>
                <input type="file" id="videoFile" accept="video/*" required>
                <button type="submit">Upload Video</button>
            </form>
            <div id="message" style="margin-top: 1rem;"></div>
        </div>
        
        <script>
            document.getElementById('uploadForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData();
                formData.append('title', document.getElementById('videoTitle').value);
                formData.append('video', document.getElementById('videoFile').files[0]);
                
                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    document.getElementById('message').innerHTML = 
                        response.ok ? 
                        '✅ ' + result.message : 
                        '❌ ' + result.error;
                        
                    if (response.ok) {
                        document.getElementById('uploadForm').reset();
                    }
                } catch (error) {
                    document.getElementById('message').innerHTML = '❌ Upload failed';
                }
            });
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

