import os
import uuid
import hmac
import mimetypes
from functools import wraps

import boto3
from flask import Flask, render_template, render_template_string, request, jsonify, Response
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

# ---------------------------------------------------------------------------
# Admin protection (set ADMIN_PASSWORD in your Render environment variables)
# Any username works; only the password is checked.
# ---------------------------------------------------------------------------
def requires_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        password = os.environ.get('ADMIN_PASSWORD')
        if not password:
            return Response(
                'Admin is locked. Set the ADMIN_PASSWORD environment variable to enable it.',
                503
            )
        auth = request.authorization
        if not auth or not hmac.compare_digest(auth.password or '', password):
            return Response(
                'Login required.', 401,
                {'WWW-Authenticate': 'Basic realm="TAWA Admin"'}
            )
        return view(*args, **kwargs)
    return wrapped


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
    # 1. Create the table if it's gone
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         title TEXT NOT NULL,
         filename TEXT NOT NULL,
         upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    
    # 2. This part checks for new columns automatically
    c.execute("PRAGMA table_info(videos)")
    columns = [column[1] for column in c.fetchall()]
    
    if 's3_key' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN s3_key TEXT")
    if 'category' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN category TEXT DEFAULT 'General'")
        
    conn.commit()
    conn.close()
init_db()

def allowed_file(filename):
    allowed_extensions = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/fix-db')
@requires_admin
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
init_db()
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@requires_admin
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
        
        # Measure size without loading the whole video into memory
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)  # Reset file pointer
        print("📁 File info:", file.filename, "Size:", size)
        
        if file.filename == '':
            print("❌ Empty filename")
            return jsonify({'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename) or 'video.mp4'
            # Unique prefix so two uploads named "movie.mp4" never overwrite each other
            s3_key = f"videos/{uuid.uuid4().hex[:8]}-{filename}"
            content_type = mimetypes.guess_type(filename)[0] or 'video/mp4'
            
            print("📤 Uploading to S3...")
            print("📦 Bucket:", AWS_BUCKET_NAME)
            print("📍 Key:", s3_key)
            
            # Upload to S3
            try:
                s3_client.upload_fileobj(
                    file,
                    AWS_BUCKET_NAME,
                    s3_key,
                    ExtraArgs={'ContentType': content_type}
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
        c.execute("SELECT id, title, filename, s3_key, upload_date, category FROM videos ORDER BY upload_date DESC")
        videos = c.fetchall()
        conn.close()
        
        video_list = []
        for video in videos:
            # Generate S3 URL for each video (older rows may have no s3_key)
            s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video[3]}" if video[3] else None
            
            video_list.append({
                'id': video[0],        # id
                'title': video[1],     # title
                'filename': video[2],  # filename
                's3_url': s3_url,      # generated URL
                'upload_date': video[4], # upload_date at index 4
                'category': video[5] or 'General'  # category at index 5
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
Disallow: /admin
Sitemap: https://tawa-streaming.onrender.com/sitemap.xml'''
    return robots_txt, 200, {'Content-Type': 'text/plain'}

# Admin route for private uploads
@app.route('/admin')
@requires_admin
def admin_panel():
    total_videos = 0
    total_categories = 0
    try:
        conn = sqlite3.connect('tawa.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*), COUNT(DISTINCT category) FROM videos")
        total_videos, total_categories = c.fetchone()
        conn.close()
    except Exception as e:
        print(f"Error computing admin stats: {e}")

    return render_template_string(r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>TAWA Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,700;12..96,800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0F172A;
    --panel: #1E293B;
    --panel-2: #172033;
    --line: #2B3A52;
    --text: #F1F5F9;
    --muted: #94A3B8;
    --sky: #38BDF8;
    --sky-deep: #0EA5E9;
    --ok: #34D399;
    --warn: #F59E0B;
    --bad: #F87171;
    --sans: 'Bricolage Grotesque', 'Segoe UI', system-ui, sans-serif;
    --mono: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { color-scheme: dark; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, .drop:focus-visible {
    outline: 2px solid var(--sky);
    outline-offset: 2px;
  }

  /* ---------- Top bar ---------- */
  .topbar {
    position: sticky; top: 0; z-index: 20;
    background: rgba(15, 23, 42, 0.88);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--line);
  }
  .topbar-inner {
    max-width: 1160px; margin: 0 auto; padding: 0.9rem 1.5rem;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  }
  .brand { display: flex; align-items: center; gap: 0.7rem; text-decoration: none; color: var(--text); }
  .brand-mark {
    width: 34px; height: 34px; border-radius: 10px;
    background: linear-gradient(140deg, var(--sky), #0369A1);
    display: grid; place-items: center;
    box-shadow: 0 0 22px rgba(56, 189, 248, 0.35);
  }
  .brand-mark svg { width: 14px; height: 14px; margin-left: 2px; fill: #0F172A; }
  .brand-name { font-weight: 800; font-size: 1.25rem; letter-spacing: 0.04em; }
  .brand-name span { font-weight: 500; color: var(--muted); margin-left: 0.4rem; letter-spacing: 0; }
  .site-link {
    color: var(--sky); text-decoration: none; font-weight: 500; font-size: 0.95rem;
    padding: 0.45rem 0.9rem; border: 1px solid var(--line); border-radius: 999px;
    transition: border-color .2s, background .2s;
  }
  .site-link:hover { border-color: var(--sky); background: rgba(56, 189, 248, 0.08); }

  /* ---------- Layout ---------- */
  .wrap { max-width: 1160px; margin: 0 auto; padding: 2.2rem 1.5rem 4rem; }
  .page-head { margin-bottom: 1.8rem; }
  .page-head h1 { font-size: clamp(1.8rem, 4vw, 2.6rem); font-weight: 800; line-height: 1.1; }
  .page-head p { color: var(--muted); margin-top: 0.4rem; max-width: 56ch; }

  /* ---------- Stats ---------- */
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
  .stat {
    background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
    padding: 1.2rem 1.3rem;
  }
  .stat-label { color: var(--muted); font-size: 0.92rem; }
  .stat-value { font-size: 2.3rem; font-weight: 800; line-height: 1.15; margin-top: 0.25rem; font-variant-numeric: tabular-nums; }
  .pill {
    display: inline-flex; align-items: center; gap: 0.5rem; margin-top: 0.7rem;
    padding: 0.35rem 0.85rem; border-radius: 999px; font-weight: 700; font-size: 0.95rem;
    background: rgba(52, 211, 153, 0.12); color: var(--ok); border: 1px solid rgba(52, 211, 153, 0.4);
  }
  .pill i { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.2); }

  /* ---------- Cards ---------- */
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 1.6rem; margin-bottom: 1.5rem; }
  .card-title { font-size: 1.25rem; font-weight: 700; }
  .card-sub { color: var(--muted); font-size: 0.95rem; margin: 0.2rem 0 1.4rem; }

  /* ---------- Upload ---------- */
  .upload-grid { display: grid; grid-template-columns: 1fr 1.25fr; gap: 1.6rem; align-items: start; }
  .field { margin-bottom: 1.1rem; }
  .field label { display: block; font-weight: 500; margin-bottom: 0.45rem; font-size: 0.95rem; }
  .input, .select {
    width: 100%; padding: 0.85rem 1rem; font: inherit; color: var(--text);
    background: var(--bg); border: 1px solid var(--line); border-radius: 10px;
    transition: border-color .2s, box-shadow .2s;
  }
  .input:focus, .select:focus { outline: none; border-color: var(--sky); box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18); }
  .select {
    appearance: none; cursor: pointer;
    background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%), linear-gradient(135deg, var(--muted) 50%, transparent 50%);
    background-position: calc(100% - 20px) 50%, calc(100% - 14px) 50%;
    background-size: 6px 6px; background-repeat: no-repeat;
  }

  /* The drop zone is framed like a cinema screen: the one bold element on the page */
  .drop {
    position: relative; aspect-ratio: 16 / 9; min-height: 190px;
    border-radius: 14px; border: 1px solid var(--line);
    background:
      radial-gradient(120% 90% at 50% 0%, rgba(56, 189, 248, 0.16), transparent 60%),
      var(--panel-2);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.5rem; text-align: center; padding: 1rem; cursor: pointer; overflow: hidden;
    transition: border-color .25s, box-shadow .25s;
  }
  .drop::after {
    content: ''; position: absolute; left: 12%; right: 12%; bottom: 0; height: 3px;
    background: var(--sky); border-radius: 3px 3px 0 0; opacity: .5;
    box-shadow: 0 0 24px 4px rgba(56, 189, 248, 0.5);
    transition: opacity .25s, left .25s, right .25s;
  }
  .drop:hover, .drop.drag { border-color: var(--sky); box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.12); }
  .drop.drag::after, .drop.has-file::after { opacity: 1; left: 0; right: 0; }
  .drop-icon { width: 46px; height: 46px; border-radius: 50%; border: 1.5px solid var(--sky); display: grid; place-items: center; }
  .drop-icon svg { width: 18px; height: 18px; fill: var(--sky); margin-left: 2px; }
  .drop-title { font-weight: 700; font-size: 1.05rem; }
  .drop-hint { color: var(--muted); font-size: 0.88rem; }
  .drop-file { font-family: var(--mono); font-size: 0.9rem; color: var(--sky); word-break: break-all; }
  .drop input { position: absolute; inset: 0; opacity: 0; pointer-events: none; }

  .progress { height: 6px; background: var(--bg); border-radius: 6px; overflow: hidden; margin-top: 1.2rem; display: none; }
  .progress.on { display: block; }
  .progress-bar { height: 100%; width: 0; background: linear-gradient(90deg, var(--sky-deep), var(--sky)); border-radius: 6px; transition: width .15s linear; }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
    font: inherit; font-weight: 700; color: #06243A; cursor: pointer;
    background: var(--sky); border: none; border-radius: 10px; padding: 0.9rem 1.6rem;
    transition: background .2s, transform .1s, opacity .2s;
  }
  .btn:hover { background: #7DD3FC; }
  .btn:active { transform: translateY(1px); }
  .btn:disabled { opacity: .55; cursor: not-allowed; }
  .form-actions { margin-top: 1.4rem; display: flex; justify-content: flex-end; }

  /* ---------- Status card ---------- */
  .status {
    display: none; margin-bottom: 1.4rem; padding: 1rem 1.2rem; border-radius: 12px;
    border: 1px solid; gap: 0.85rem; align-items: flex-start;
  }
  .status.show { display: flex; }
  .status-dot { flex: none; width: 12px; height: 12px; border-radius: 50%; margin-top: 0.4rem; }
  .status-title { font-weight: 700; }
  .status-text { font-size: 0.95rem; opacity: .9; word-break: break-word; }
  .status.loading { background: rgba(245, 158, 11, 0.1); border-color: rgba(245, 158, 11, 0.5); color: #FCD34D; }
  .status.loading .status-dot { background: var(--warn); animation: pulse 1.2s ease-in-out infinite; }
  .status.success { background: rgba(52, 211, 153, 0.1); border-color: rgba(52, 211, 153, 0.5); color: #6EE7B7; }
  .status.success .status-dot { background: var(--ok); }
  .status.error { background: rgba(248, 113, 113, 0.1); border-color: rgba(248, 113, 113, 0.5); color: #FCA5A5; }
  .status.error .status-dot { background: var(--bad); }
  @keyframes pulse { 50% { opacity: .3; transform: scale(.8); } }

  /* ---------- Library ---------- */
  .lib-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.2rem; }
  .lib-head .card-sub { margin-bottom: 0; }
  .lib-tools { display: flex; gap: 0.6rem; }
  .lib-tools .input { width: 250px; padding: 0.65rem 0.9rem; }
  .btn-ghost {
    font: inherit; font-weight: 500; color: var(--text); cursor: pointer;
    background: transparent; border: 1px solid var(--line); border-radius: 10px; padding: 0.6rem 1rem;
    transition: border-color .2s;
  }
  .btn-ghost:hover { border-color: var(--sky); }
  .table-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
  table { width: 100%; border-collapse: collapse; min-width: 720px; }
  th { text-align: left; font-weight: 500; font-size: 0.88rem; color: var(--muted); padding: 0.85rem 1.1rem; background: var(--panel-2); border-bottom: 1px solid var(--line); }
  td { padding: 0.95rem 1.1rem; border-bottom: 1px solid var(--line); vertical-align: middle; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: rgba(56, 189, 248, 0.04); }
  th.right, td.right { text-align: right; }
  .title-cell { display: flex; align-items: center; gap: 0.85rem; min-width: 0; }
  .thumb {
    flex: none; width: 56px; aspect-ratio: 16 / 9; border-radius: 6px;
    display: grid; place-items: center; font-weight: 800; font-size: 0.95rem; color: var(--sky);
    background: linear-gradient(140deg, #243247, #172033); border: 1px solid var(--line);
  }
  .title-text { font-weight: 700; overflow: hidden; text-overflow: ellipsis; }
  .title-date { color: var(--muted); font-size: 0.82rem; font-weight: 400; display: block; }
  .badge {
    display: inline-block; padding: 0.28rem 0.7rem; border-radius: 999px; font-size: 0.85rem; font-weight: 500;
    background: #0B1220; border: 1px solid var(--line); color: var(--muted);
  }
  .badge[data-tint="trending"] { color: #7DD3FC; border-color: rgba(56, 189, 248, 0.45); background: rgba(56, 189, 248, 0.08); }
  .badge[data-tint="movies"]   { color: #C4B5FD; border-color: rgba(167, 139, 250, 0.45); background: rgba(167, 139, 250, 0.08); }
  .badge[data-tint="shows"]    { color: #5EEAD4; border-color: rgba(45, 212, 191, 0.45); background: rgba(45, 212, 191, 0.08); }
  .badge[data-tint="continue"] { color: #FCD34D; border-color: rgba(251, 191, 36, 0.45); background: rgba(251, 191, 36, 0.08); }
  .filename { font-family: var(--mono); font-size: 0.85rem; color: #CBD5E1; word-break: break-all; }
  .test-link {
    display: inline-block; color: var(--sky); text-decoration: none; font-weight: 700; font-size: 0.92rem;
    padding: 0.4rem 0.85rem; border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 8px; white-space: nowrap;
    transition: background .2s;
  }
  .test-link:hover { background: rgba(56, 189, 248, 0.12); }
  .muted-cell { color: var(--muted); font-size: 0.9rem; }

  .skeleton td > div { height: 14px; border-radius: 6px; background: linear-gradient(90deg, #243247 25%, #2D3E58 50%, #243247 75%); background-size: 200% 100%; animation: shimmer 1.3s linear infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  .empty { text-align: center; padding: 3rem 1rem; color: var(--muted); }
  .empty strong { display: block; color: var(--text); font-size: 1.1rem; margin-bottom: 0.3rem; }

  @media (max-width: 860px) {
    .stats { grid-template-columns: 1fr; }
    .upload-grid { grid-template-columns: 1fr; }
    .lib-tools { width: 100%; }
    .lib-tools .input { flex: 1; width: auto; }
  }
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="/admin" aria-label="TAWA Admin home">
      <span class="brand-mark"><svg viewBox="0 0 10 12"><path d="M0 0l10 6-10 6z"/></svg></span>
      <span class="brand-name">TAWA<span>Admin</span></span>
    </a>
    <a class="site-link" href="/" target="_blank" rel="noopener">View Main Site →</a>
  </div>
</header>

<main class="wrap">
  <div class="page-head">
    <h1>Your catalogue</h1>
    <p>Add new titles to the cloud and check that every one of them streams before your viewers find it.</p>
  </div>

  <section class="stats" aria-label="Platform stats">
    <div class="stat">
      <div class="stat-label">Total Cloud Titles</div>
      <div class="stat-value" id="statTitles">{{ total_videos }}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Active Categories</div>
      <div class="stat-value" id="statCats">{{ total_categories }}</div>
    </div>
    <div class="stat">
      <div class="stat-label">S3 Storage Status</div>
      <div class="pill"><i></i>Connected</div>
    </div>
  </section>

  <section class="card" aria-labelledby="uploadTitle">
    <h2 class="card-title" id="uploadTitle">Add a title</h2>
    <p class="card-sub">Pick a row on the home page, name the video, and drop the file in.</p>

    <div id="statusCard" class="status" role="status" aria-live="polite">
      <span class="status-dot"></span>
      <div>
        <div class="status-title" id="statusTitle"></div>
        <div class="status-text" id="statusText"></div>
      </div>
    </div>

    <form id="uploadForm" novalidate>
      <div class="upload-grid">
        <div>
          <div class="field">
            <label for="videoTitle">Title</label>
            <input class="input" type="text" id="videoTitle" placeholder="e.g. Copperbelt Nights, Episode 1" maxlength="120" required>
          </div>
          <div class="field">
            <label for="videoCategory">Home page row</label>
            <select class="select" id="videoCategory" required>
              <option value="">Choose a row</option>
              <option value="Trending Now">Trending Now</option>
              <option value="Popular Movies">Popular Movies</option>
              <option value="TV Shows">TV Shows</option>
              <option value="Continue Watching">Continue Watching</option>
            </select>
          </div>
        </div>

        <div>
          <div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose a video file">
            <input type="file" id="videoFile" accept="video/mp4,video/x-msvideo,video/quicktime,video/x-matroska,video/webm,.mp4,.avi,.mov,.mkv,.webm" tabindex="-1">
            <div class="drop-icon"><svg viewBox="0 0 10 12"><path d="M0 0l10 6-10 6z"/></svg></div>
            <div class="drop-title" id="dropTitle">Drop your video here</div>
            <div class="drop-hint" id="dropHint">or click to browse. MP4, MOV, MKV, AVI or WEBM.</div>
            <div class="drop-file" id="dropFile"></div>
          </div>
          <div class="progress" id="progress"><div class="progress-bar" id="progressBar"></div></div>
        </div>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn" id="uploadBtn">Upload to cloud</button>
      </div>
    </form>
  </section>

  <section class="card" aria-labelledby="libTitle">
    <div class="lib-head">
      <div>
        <h2 class="card-title" id="libTitle">Library</h2>
        <p class="card-sub" id="libCount">Loading your titles…</p>
      </div>
      <div class="lib-tools">
        <input class="input" type="search" id="search" placeholder="Search titles or rows" aria-label="Search library">
        <button class="btn-ghost" type="button" id="refresh">Refresh</button>
      </div>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Category</th>
            <th>System Filename</th>
            <th class="right">Actions</th>
          </tr>
        </thead>
        <tbody id="libBody"></tbody>
      </table>
    </div>
  </section>
</main>

<script>
  const $ = (id) => document.getElementById(id);
  const ALLOWED = ['mp4', 'avi', 'mov', 'mkv', 'webm'];
  const TINTS = { 'Trending Now': 'trending', 'Popular Movies': 'movies', 'TV Shows': 'shows', 'Continue Watching': 'continue' };
  let library = [];
  let chosenFile = null;

  /* ---------- Status card ---------- */
  function setStatus(kind, title, text) {
    const card = $('statusCard');
    card.className = 'status show ' + kind;
    $('statusTitle').textContent = title;
    $('statusText').textContent = text || '';
  }
  function clearStatus() { $('statusCard').className = 'status'; }

  /* ---------- File picking ---------- */
  function formatSize(bytes) {
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(2) + ' GB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }
  function pickFile(file) {
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setStatus('error', 'That file type is not supported', 'Use an MP4, MOV, MKV, AVI or WEBM video.');
      return;
    }
    chosenFile = file;
    clearStatus();
    $('drop').classList.add('has-file');
    $('dropTitle').textContent = 'Ready to upload';
    $('dropHint').textContent = 'Click to choose a different file.';
    $('dropFile').textContent = file.name + ' (' + formatSize(file.size) + ')';
  }
  const drop = $('drop');
  drop.addEventListener('click', () => $('videoFile').click());
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('videoFile').click(); } });
  $('videoFile').addEventListener('change', (e) => pickFile(e.target.files[0]));
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', (e) => pickFile(e.dataTransfer.files[0]));

  /* ---------- Upload (XHR so a big video shows real progress) ---------- */
  function resetForm() {
    $('uploadForm').reset();
    chosenFile = null;
    drop.classList.remove('has-file');
    $('dropTitle').textContent = 'Drop your video here';
    $('dropHint').textContent = 'or click to browse. MP4, MOV, MKV, AVI or WEBM.';
    $('dropFile').textContent = '';
  }
  function endUpload() {
    $('uploadBtn').disabled = false;
    $('uploadBtn').textContent = 'Upload to cloud';
    $('progress').classList.remove('on');
    $('progressBar').style.width = '0';
  }

  $('uploadForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const title = $('videoTitle').value.trim();
    const category = $('videoCategory').value;
    if (!title) return setStatus('error', 'Add a title', 'Give the video a name viewers will see.');
    if (!category) return setStatus('error', 'Choose a row', 'Pick where this video should appear on the home page.');
    if (!chosenFile) return setStatus('error', 'Choose a video', 'Drop a file into the screen or click it to browse.');

    const data = new FormData();
    data.append('title', title);
    data.append('category', category);
    data.append('video', chosenFile);

    $('uploadBtn').disabled = true;
    $('uploadBtn').textContent = 'Uploading…';
    $('progress').classList.add('on');
    setStatus('loading', 'Uploading ' + title, 'Sending 0% of ' + formatSize(chosenFile.size) + '. Keep this tab open.');

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      $('progressBar').style.width = pct + '%';
      if (pct < 100) {
        setStatus('loading', 'Uploading ' + title, 'Sent ' + pct + '% of ' + formatSize(ev.total) + '. Keep this tab open.');
      } else {
        setStatus('loading', 'Saving to cloud storage', 'The file reached the server. Moving it to S3 now, this can take a minute.');
      }
    };
    xhr.onload = () => {
      let result = {};
      try { result = JSON.parse(xhr.responseText); } catch (err) { /* non-JSON reply */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        setStatus('success', title + ' is live', 'Saved to ' + category + '. Use Test Stream in the library to check playback.');
        resetForm();
        loadLibrary();
      } else if (xhr.status === 401) {
        setStatus('error', 'Login expired', 'Reload the page and sign in again.');
      } else {
        setStatus('error', 'Upload failed', result.error || ('The server replied with status ' + xhr.status + '. Try again.'));
      }
      endUpload();
    };
    xhr.onerror = () => {
      setStatus('error', 'Connection lost', 'The upload did not finish. Check your internet and try again.');
      endUpload();
    };
    xhr.send(data);
  });

  /* ---------- Library ---------- */
  function showSkeleton() {
    const rows = [];
    for (let i = 0; i < 4; i++) {
      rows.push('<tr class="skeleton"><td><div style="width:70%"></div></td><td><div style="width:60%"></div></td><td><div style="width:80%"></div></td><td><div style="width:50%;margin-left:auto"></div></td></tr>');
    }
    $('libBody').innerHTML = rows.join('');
  }

  function cell(child, cls) {
    const td = document.createElement('td');
    if (cls) td.className = cls;
    td.appendChild(child);
    return td;
  }

  function renderLibrary() {
    const q = $('search').value.trim().toLowerCase();
    const list = library.filter((v) => !q || v.title.toLowerCase().includes(q) || (v.category || '').toLowerCase().includes(q));
    const body = $('libBody');
    body.textContent = '';

    if (!list.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'empty';
      const strong = document.createElement('strong');
      strong.textContent = library.length ? 'No titles match your search' : 'Your library is empty';
      td.appendChild(strong);
      td.appendChild(document.createTextNode(library.length ? 'Try a different word.' : 'Upload your first video above and it will appear here.'));
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }

    list.forEach((v) => {
      const tr = document.createElement('tr');

      // Title (built with textContent so titles can never inject HTML)
      const wrap = document.createElement('div');
      wrap.className = 'title-cell';
      const thumb = document.createElement('div');
      thumb.className = 'thumb';
      thumb.textContent = (v.title || '?').trim().charAt(0).toUpperCase();
      const info = document.createElement('div');
      info.style.minWidth = '0';
      const name = document.createElement('span');
      name.className = 'title-text';
      name.textContent = v.title;
      const date = document.createElement('span');
      date.className = 'title-date';
      const d = new Date((v.upload_date || '').replace(' ', 'T') + 'Z');
      date.textContent = isNaN(d) ? '' : 'Added ' + d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
      info.appendChild(name);
      info.appendChild(date);
      wrap.appendChild(thumb);
      wrap.appendChild(info);
      tr.appendChild(cell(wrap));

      // Category badge
      const badge = document.createElement('span');
      badge.className = 'badge';
      if (TINTS[v.category]) badge.dataset.tint = TINTS[v.category];
      badge.textContent = v.category || 'General';
      tr.appendChild(cell(badge));

      // Filename
      const file = document.createElement('span');
      file.className = 'filename';
      file.textContent = v.filename;
      tr.appendChild(cell(file));

      // Actions
      let action;
      if (v.s3_url) {
        action = document.createElement('a');
        action.className = 'test-link';
        action.href = v.s3_url;
        action.target = '_blank';
        action.rel = 'noopener';
        action.textContent = 'Test Stream ↗';
      } else {
        action = document.createElement('span');
        action.className = 'muted-cell';
        action.textContent = 'No cloud file';
      }
      tr.appendChild(cell(action, 'right'));

      body.appendChild(tr);
    });
  }

  async function loadLibrary() {
    showSkeleton();
    try {
      const res = await fetch('/videos', { cache: 'no-store' });
      if (!res.ok) throw new Error('Status ' + res.status);
      library = await res.json();
      const cats = new Set(library.map((v) => v.category).filter(Boolean));
      $('statTitles').textContent = library.length;
      $('statCats').textContent = cats.size;
      $('libCount').textContent = library.length === 1 ? '1 title in the cloud' : library.length + ' titles in the cloud';
      renderLibrary();
    } catch (err) {
      $('libBody').innerHTML = '';
      $('libCount').textContent = 'Could not load the library.';
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'empty';
      const strong = document.createElement('strong');
      strong.textContent = 'Library unavailable';
      td.appendChild(strong);
      td.appendChild(document.createTextNode('Check your connection, then press Refresh.'));
      tr.appendChild(td);
      $('libBody').appendChild(tr);
    }
  }

  $('search').addEventListener('input', renderLibrary);
  $('refresh').addEventListener('click', loadLibrary);
  document.addEventListener('DOMContentLoaded', loadLibrary);
</script>
</body>
</html>
''', total_videos=total_videos, total_categories=total_categories)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
