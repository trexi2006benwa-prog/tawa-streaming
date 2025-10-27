import os
import boto3
from flask import Flask, render_template, request, jsonify
import sqlite3
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

app = Flask(__name__)

# AWS S3 Configuration
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME', 'tawa-streaming')
AWS_REGION = 'eu-north-1'  # Stockholm region


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
        
        if 'category' not in columns:
            c.execute("ALTER TABLE videos ADD COLUMN category TEXT DEFAULT 'General'")
            print("✅ Added category column to existing database")
        else:
            print("✅ All columns already exist")
            
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
        print("=== UPLOAD DEBUG START ===")
        print("AWS_BUCKET_NAME:", AWS_BUCKET_NAME)
        print("AWS_REGION:", AWS_REGION)
        
        if 'video' not in request.files:
            print("❌ No video file in request")
            return jsonify({'error': 'No video file'}), 400
        
        file = request.files['video']
        title = request.form.get('title', 'Untitled')
        category = request.form.get('category', 'General')
        
        print("📁 File info:", file.filename, "Size:", len(file.read()) if file else 0)
        file.seek(0)  # Reset file pointer
        
        if file.filename == '':
            print("❌ Empty filename")
            return jsonify({'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            s3_key = f"videos/{filename}"
            
            print("📤 Uploading to S3...")
            print("📦 Bucket:", AWS_BUCKET_NAME)
            print("📍 Key:", s3_key)
            
            # Upload to S3
            try:
                s3_client.upload_fileobj(
                    file,
                    AWS_BUCKET_NAME,
                    s3_key,
                    ExtraArgs={'ContentType': 'video/mp4'}
                )
                print("✅ S3 upload successful!")
            except ClientError as e:
                print("❌ S3 upload failed:", str(e))
                return jsonify({'error': f'S3 upload failed: {str(e)}'}), 500
            
            # Save to database
            conn = sqlite3.connect('tawa.db')
            c = conn.cursor()
            c.execute("INSERT INTO videos (title, filename, s3_key, category) VALUES (?, ?, ?, ?)", 
                     (title, filename, s3_key, category))
            conn.commit()
            conn.close()
            
            # Generate the S3 URL for the response
            s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
            print("🎉 Upload completed successfully!")
            
            return jsonify({
                'message': 'Video uploaded successfully to cloud!', 
                'filename': filename,
                's3_url': s3_url,
                'category': category
            })
        else:
            print("❌ File type not allowed")
            return jsonify({'error': 'File type not allowed. Please use MP4, AVI, MOV, MKV, or WEBM.'}), 400
            
    except Exception as e:
        print("💥 Unexpected error:", str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        print("=== UPLOAD DEBUG END ===")

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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background: #0F172A;
                color: white;
                font-family: 'Arial', sans-serif;
                min-height: 100vh;
            }
            
            /* Header Styles */
            .admin-header {
                background: linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(15, 23, 42, 0.8) 100%);
                backdrop-filter: blur(10px);
                padding: 1rem 2rem;
                position: sticky;
                top: 0;
                z-index: 100;
                border-bottom: 1px solid #334155;
            }
            
            .header-content {
                max-width: 1200px;
                margin: 0 auto;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            
            .logo {
                font-size: 2rem;
                font-weight: bold;
                background: linear-gradient(45deg, #3B82F6, #8B5CF6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .nav-menu {
                display: flex;
                gap: 2rem;
                list-style: none;
            }
            
            .nav-menu a {
                color: #E2E8F0;
                text-decoration: none;
                font-weight: 500;
                transition: color 0.3s ease;
                cursor: pointer;
            }
            
            .nav-menu a:hover {
                color: #3B82F6;
            }
            
            .nav-menu a.active {
                color: #3B82F6;
                font-weight: 600;
            }
            
            /* Hero Section */
            .hero-section {
                background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                padding: 4rem 2rem;
                text-align: center;
                border-bottom: 1px solid #334155;
            }
            
            .hero-content {
                max-width: 800px;
                margin: 0 auto;
            }
            
            .hero-title {
                font-size: 3rem;
                font-weight: bold;
                margin-bottom: 1rem;
                background: linear-gradient(45deg, #E2E8F0, #94A3B8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .hero-subtitle {
                font-size: 1.2rem;
                color: #94A3B8;
                margin-bottom: 2rem;
                line-height: 1.6;
            }
            
            .upload-btn {
                background: linear-gradient(45deg, #3B82F6, #2563EB);
                color: white;
                padding: 1rem 2rem;
                border: none;
                border-radius: 8px;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .upload-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(37, 99, 235, 0.3);
            }
            
            /* Main Content */
            .admin-main {
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
            }
            
            .section {
                margin-bottom: 3rem;
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
            }
            
            .section-title {
                font-size: 1.5rem;
                font-weight: 600;
                color: #E2E8F0;
            }
            
            .view-all {
                color: #3B82F6;
                text-decoration: none;
                font-weight: 500;
                cursor: pointer;
            }
            
            /* Upload Modal */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                z-index: 1000;
                backdrop-filter: blur(5px);
            }
            
            .modal-content {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: #1E293B;
                padding: 2rem;
                border-radius: 12px;
                width: 90%;
                max-width: 500px;
                border: 1px solid #334155;
            }
            
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
            }
            
            .modal-title {
                font-size: 1.5rem;
                font-weight: 600;
                color: #E2E8F0;
            }
            
            .close-btn {
                background: none;
                border: none;
                color: #94A3B8;
                font-size: 1.5rem;
                cursor: pointer;
            }
            
            .form-group {
                margin-bottom: 1rem;
            }
            
            .form-label {
                display: block;
                margin-bottom: 0.5rem;
                color: #E2E8F0;
                font-weight: 500;
            }
            
            .form-input {
                width: 100%;
                padding: 0.8rem;
                background: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                color: white;
                font-size: 1rem;
            }
            
            .form-input:focus {
                outline: none;
                border-color: #3B82F6;
            }
            
            .file-input-wrapper {
                position: relative;
                overflow: hidden;
                display: inline-block;
                width: 100%;
            }
            
            .file-input-label {
                display: block;
                padding: 1rem;
                background: #0F172A;
                border: 2px dashed #475569;
                border-radius: 6px;
                text-align: center;
                color: #94A3B8;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .file-input-label:hover {
                border-color: #3B82F6;
                color: #3B82F6;
            }
            
            .submit-btn {
                width: 100%;
                padding: 1rem;
                background: linear-gradient(45deg, #3B82F6, #2563EB);
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                margin-top: 1rem;
            }
            
            /* Videos Grid */
            .videos-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 1.5rem;
            }
            
            .video-card {
                background: #1E293B;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #334155;
                transition: all 0.3s ease;
            }
            
            .video-card:hover {
                transform: translateY(-5px);
                border-color: #3B82F6;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }
            
            .video-thumbnail {
                width: 100%;
                height: 160px;
                background: linear-gradient(45deg, #475569, #334155);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 3rem;
            }
            
            .video-info {
                padding: 1rem;
            }
            
            .video-title {
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: #E2E8F0;
            }
            
            .video-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 0.9rem;
                color: #94A3B8;
            }
            
            .video-category {
                background: #3B82F6;
                color: white;
                padding: 0.3rem 0.6rem;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: 600;
            }
            
            /* Footer */
            .admin-footer {
                background: #0F172A;
                padding: 2rem;
                text-align: center;
                border-top: 1px solid #334155;
                margin-top: 4rem;
            }
            
            .footer-text {
                color: #64748B;
                font-size: 0.9rem;
            }
            
            /* Message Styles */
            .message {
                padding: 1rem;
                border-radius: 6px;
                margin-top: 1rem;
                text-align: center;
                font-weight: 500;
            }
            
            .message.success {
                background: rgba(34, 197, 94, 0.1);
                border: 1px solid #22C55E;
                color: #22C55E;
            }
            
            .message.error {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid #EF4444;
                color: #EF4444;
            }
            
            .message.info {
                background: rgba(59, 130, 246, 0.1);
                border: 1px solid #3B82F6;
                color: #3B82F6;
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <header class="admin-header">
            <div class="header-content">
                <div class="logo">TAWA</div>
                <nav>
                    <ul class="nav-menu">
                        <li><a class="active">Home</a></li>
                        <li><a>Trending</a></li>
                        <li><a>TV Shows</a></li>
                        <li><a>Movies</a></li>
                        <li><a>New & Popular</a></li>
                        <li><a>My List</a></li>
                    </ul>
                </nav>
            </div>
        </header>

        <!-- Hero Section -->
        <section class="hero-section">
            <div class="hero-content">
                <h1 class="hero-title">Admin Dashboard</h1>
                <p class="hero-subtitle">
                    Manage your video content, upload new videos, and organize them across different sections of your streaming platform.
                </p>
                <button class="upload-btn" onclick="openUploadModal()">Upload New Video</button>
            </div>
        </section>

        <!-- Main Content -->
        <main class="admin-main">
            <!-- Recent Uploads Section -->
            <section class="section">
                <div class="section-header">
                    <h2 class="section-title">Continue Managing</h2>
                    <a class="view-all">View All</a>
                </div>
                <div class="videos-grid" id="recentVideos">
                    <!-- Recent videos will be loaded here -->
                </div>
            </section>

            <!-- All Videos Section -->
            <section class="section">
                <div class="section-header">
                    <h2 class="section-title">All Videos</h2>
                    <a class="view-all">View All</a>
                </div>
                <div class="videos-grid" id="allVideos">
                    <!-- All videos will be loaded here -->
                </div>
            </section>
        </main>

        <!-- Upload Modal -->
        <div id="uploadModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3 class="modal-title">Upload New Video</h3>
                    <button class="close-btn" onclick="closeUploadModal()">&times;</button>
                </div>
                <form id="uploadForm">
                    <div class="form-group">
                        <label class="form-label">Video Title</label>
                        <input type="text" class="form-input" id="videoTitle" placeholder="Enter video title" required>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Category</label>
                        <select class="form-input" id="videoCategory" required>
                            <option value="">Select Category</option>
                            <option value="Trending">Trending</option>
                            <option value="Movies">Movies</option>
                            <option value="TV Shows">TV Shows</option>
                            <option value="New & Popular">New & Popular</option>
                            <option value="My List">My List</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Video File</label>
                        <div class="file-input-wrapper">
                            <input type="file" id="videoFile" accept="video/*" required>
                            <label for="videoFile" class="file-input-label">
                                Choose Video File (MP4, AVI, MOV, MKV, WEBM)
                            </label>
                        </div>
                        <div style="color: #64748B; font-size: 0.9rem; margin-top: 0.5rem; text-align: center;" id="fileName">
                            No file selected
                        </div>
                    </div>
                    
                    <button type="submit" class="submit-btn" id="uploadBtn">
                        Upload Video
                    </button>
                </form>
                <div id="message" class="message"></div>
            </div>
        </div>

        <!-- Footer -->
        <footer class="admin-footer">
            <p class="footer-text">© 2023 TAWA Streaming Platform. All rights reserved.</p>
        </footer>

        <script>
            // Modal Functions
            function openUploadModal() {
                document.getElementById('uploadModal').style.display = 'block';
            }
            
            function closeUploadModal() {
                document.getElementById('uploadModal').style.display = 'none';
                document.getElementById('uploadForm').reset();
                document.getElementById('fileName').textContent = 'No file selected';
                document.getElementById('message').innerHTML = '';
                document.getElementById('message').className = 'message';
            }
            
            // File input display
            document.getElementById('videoFile').addEventListener('change', function(e) {
                const fileName = this.files[0] ? this.files[0].name : 'No file selected';
                document.getElementById('fileName').textContent = fileName;
            });
            
            // Form submission
            document.getElementById('uploadForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const submitBtn = document.getElementById('uploadBtn');
                const messageDiv = document.getElementById('message');
                const originalText = submitBtn.textContent;
                
                // Show loading state
                submitBtn.disabled = true;
                submitBtn.textContent = 'Uploading...';
                messageDiv.className = 'message info';
                messageDiv.innerHTML = '⏳ Uploading video to cloud storage...';
                
                const formData = new FormData();
                formData.append('title', document.getElementById('videoTitle').value);
                formData.append('category', document.getElementById('videoCategory').value);
                formData.append('video', document.getElementById('videoFile').files[0]);
                
                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    let result;
                    try {
                        result = await response.json();
                    } catch (jsonError) {
                        throw new Error('Server returned invalid response');
                    }
                    
                    if (response.ok) {
                        messageDiv.className = 'message success';
                        messageDiv.innerHTML = '✅ ' + result.message;
                        document.getElementById('uploadForm').reset();
                        document.getElementById('fileName').textContent = 'No file selected';
                        setTimeout(() => {
                            closeUploadModal();
                            loadVideos();
                        }, 2000);
                    } else {
                        messageDiv.className = 'message error';
                        messageDiv.innerHTML = '❌ ' + (result.error || 'Upload failed');
                    }
                } catch (error) {
                    console.error('Upload error:', error);
                    messageDiv.className = 'message error';
                    messageDiv.innerHTML = '❌ Upload failed: ' + error.message;
                } finally {
                    // Reset button state
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            });
            
            // Load videos
            async function loadVideos() {
                try {
                    const response = await fetch('/videos');
                    const videos = await response.json();
                    
                    const recentContainer = document.getElementById('recentVideos');
                    const allContainer = document.getElementById('allVideos');
                    
                    if (videos.length === 0) {
                        recentContainer.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #64748B; padding: 2rem;">No videos uploaded yet</div>';
                        allContainer.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #64748B; padding: 2rem;">No videos uploaded yet</div>';
                        return;
                    }
                    
                    // Recent videos (last 4)
                    const recentVideos = videos.slice(0, 4);
                    recentContainer.innerHTML = recentVideos.map(video => `
                        <div class="video-card">
                            <div class="video-thumbnail">🎥</div>
                            <div class="video-info">
                                <div class="video-title">${video.title}</div>
                                <div class="video-meta">
                                    <span class="video-category">${video.category}</span>
                                    <span>${new Date(video.upload_date).toLocaleDateString()}</span>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    
                    // All videos
                    allContainer.innerHTML = videos.map(video => `
                        <div class="video-card">
                            <div class="video-thumbnail">🎥</div>
                            <div class="video-info">
                                <div class="video-title">${video.title}</div>
                                <div class="video-meta">
                                    <span class="video-category">${video.category}</span>
                                    <span>${new Date(video.upload_date).toLocaleDateString()}</span>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    
                } catch (error) {
                    console.error('Error loading videos:', error);
                }
            }
            
            // Load videos when page loads
            document.addEventListener('DOMContentLoaded', loadVideos);
            
            // Close modal when clicking outside
            window.addEventListener('click', function(event) {
                const modal = document.getElementById('uploadModal');
                if (event.target === modal) {
                    closeUploadModal();
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






