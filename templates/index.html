import os
import re
import time
import uuid
import hmac
import hashlib
import secrets
import datetime
import mimetypes
from functools import wraps

import boto3
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, Response, session, redirect
from pgcompat import sqlite3
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

        if 'thumb_key' not in columns:
            c.execute("ALTER TABLE videos ADD COLUMN thumb_key TEXT")
            print("✅ Added thumb_key column to existing database")
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
    if 'thumb_key' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN thumb_key TEXT")
        
    conn.commit()
    conn.close()
init_db()

# ---------------------------------------------------------------------------
# Accounts (phone number + SMS code), K15 subscription, and live
# ---------------------------------------------------------------------------
PRICE_KWACHA = 15
SUBSCRIPTION_DAYS = 30

app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=not os.environ.get('DEV_MODE'),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=90),
)


def db():
    conn = sqlite3.connect('tawa.db')
    conn.row_factory = sqlite3.Row
    return conn


def init_accounts_db():
    conn = db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            paid_until TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS otps (
            phone TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            expires REAL NOT NULL,
            attempts INTEGER DEFAULT 0,
            sent_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS payments (
            reference TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS live (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            title TEXT, hls_url TEXT, is_live INTEGER DEFAULT 0);
        INSERT OR IGNORE INTO live (id, title, hls_url, is_live) VALUES (1, '', '', 0);
    ''')
    conn.commit()
    conn.close()
init_accounts_db()


def utcnow():
    return datetime.datetime.utcnow()


def json_body():
    """JSON only. A cross-site HTML form cannot send this, which blocks CSRF."""
    return request.get_json(silent=True) or {}


def normalize_phone(raw):
    digits = re.sub(r'[\s\-()]', '', raw or '')
    m = re.fullmatch(r'(?:\+?260|0)?(\d{9})', digits)
    return '+260' + m.group(1) if m else None


def hash_code(phone, code):
    return hashlib.sha256(f'{app.secret_key}:{phone}:{code}'.encode()).hexdigest()


def send_sms(phone, text):
    """Africa's Talking. Without keys it only works when DEV_MODE=1 (code goes to the log)."""
    key = os.environ.get('AT_API_KEY')
    if not key:
        if os.environ.get('DEV_MODE'):
            print(f'DEV SMS to {phone}: {text}')
            return True
        return False
    data = {'username': os.environ.get('AT_USERNAME', 'sandbox'), 'to': phone, 'message': text}
    if os.environ.get('AT_SENDER'):
        data['from'] = os.environ['AT_SENDER']
    try:
        r = requests.post('https://api.africastalking.com/version1/messaging',
                          headers={'apiKey': key, 'Accept': 'application/json'},
                          data=data, timeout=15)
        return r.status_code in (200, 201)
    except requests.RequestException as e:
        print('SMS error:', e)
        return False


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    conn = db()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    conn.close()
    return row


def is_subscribed(user):
    return bool(user and user['paid_until'] and
                datetime.datetime.fromisoformat(user['paid_until']) > utcnow())


def grant_days(phone, days):
    """Add days of access, stacking on top of any time already paid for."""
    conn = db()
    conn.execute('INSERT OR IGNORE INTO users (phone) VALUES (?)', (phone,))
    row = conn.execute('SELECT paid_until FROM users WHERE phone = ?', (phone,)).fetchone()
    base = utcnow()
    if row['paid_until']:
        base = max(base, datetime.datetime.fromisoformat(row['paid_until']))
    new_until = (base + datetime.timedelta(days=days)).isoformat()
    conn.execute('UPDATE users SET paid_until = ? WHERE phone = ?', (new_until, phone))
    conn.commit()
    conn.close()
    return new_until


def me_payload(user):
    if not user:
        return {'signed_in': False, 'price': PRICE_KWACHA, 'sms': bool(os.environ.get('AT_API_KEY'))}
    return {'signed_in': True, 'phone': user['phone'], 'subscribed': is_subscribed(user),
            'paid_until': user['paid_until'], 'price': PRICE_KWACHA,
            'sms': bool(os.environ.get('AT_API_KEY'))}


@app.route('/auth/send-code', methods=['POST'])
def send_code():
    phone = normalize_phone(json_body().get('phone'))
    if not phone:
        return jsonify({'error': 'Enter a valid Zambian number, like 097 123 4567.'}), 400
    if not os.environ.get('AT_API_KEY'):
        # No SMS service yet: the admin makes the code in /admin and sends it by hand
        return jsonify({'ok': True, 'phone': phone, 'manual': True})
    conn = db()
    row = conn.execute('SELECT sent_at FROM otps WHERE phone = ?', (phone,)).fetchone()
    if row and time.time() - row['sent_at'] < 60:
        conn.close()
        return jsonify({'error': 'Wait a minute before asking for another code.'}), 429
    code = f'{secrets.randbelow(10**6):06d}'
    if not send_sms(phone, f'Your TAWA code is {code}. It expires in 10 minutes.'):
        conn.close()
        return jsonify({'error': 'We could not send the text. Try again in a moment.'}), 503
    conn.execute('INSERT OR REPLACE INTO otps (phone, code_hash, expires, attempts, sent_at) VALUES (?, ?, ?, 0, ?)',
                 (phone, hash_code(phone, code), time.time() + 600, time.time()))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'phone': phone})


@app.route('/auth/verify', methods=['POST'])
def verify_code():
    body = json_body()
    phone = normalize_phone(body.get('phone'))
    code = re.sub(r'\D', '', str(body.get('code') or ''))
    conn = db()
    row = conn.execute('SELECT * FROM otps WHERE phone = ?', (phone,)).fetchone() if phone else None
    if not row or row['expires'] < time.time():
        conn.close()
        return jsonify({'error': 'That code is not right or has expired. Ask TAWA for a new one.'}), 400
    if row['attempts'] >= 5:
        conn.close()
        return jsonify({'error': 'Too many tries. Ask for a new code.'}), 429
    conn.execute('UPDATE otps SET attempts = attempts + 1 WHERE phone = ?', (phone,))
    if not hmac.compare_digest(row['code_hash'], hash_code(phone, code)):
        conn.commit()
        conn.close()
        return jsonify({'error': 'That code is not right. Check the text and try again.'}), 400
    conn.execute('DELETE FROM otps WHERE phone = ?', (phone,))
    conn.execute('INSERT OR IGNORE INTO users (phone) VALUES (?)', (phone,))
    user = conn.execute('SELECT * FROM users WHERE phone = ?', (phone,)).fetchone()
    conn.commit()
    conn.close()
    session.clear()
    session.permanent = True
    session['uid'] = user['id']
    return jsonify(me_payload(user))


@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/me')
def me():
    return jsonify(me_payload(current_user()))


def charge_mobile_money(phone, amount, reference):
    """TODO: connect your mobile money provider here (Lipila, DPO, MTN MoMo API, Airtel Money API...).

    It must send a payment prompt for `amount` kwacha to `phone`, using `reference` as the
    payment's ID, and set the provider's callback URL to POST /pay/webhook.
    Until this is filled in, subscribers are activated with /admin/grant."""
    raise NotImplementedError


@app.route('/pay/start', methods=['POST'])
def pay_start():
    user = current_user()
    if not user:
        return jsonify({'error': 'Sign in first.'}), 401
    reference = 'TAWA-' + uuid.uuid4().hex[:12]
    conn = db()
    conn.execute('INSERT INTO payments (reference, phone, amount) VALUES (?, ?, ?)',
                 (reference, user['phone'], PRICE_KWACHA))
    conn.commit()
    conn.close()
    try:
        charge_mobile_money(user['phone'], PRICE_KWACHA, reference)
    except NotImplementedError:
        return jsonify({'error': 'Payments are not switched on yet. Please try again soon.'}), 503
    except Exception as e:
        print('Payment error:', e)
        return jsonify({'error': 'The payment could not start. Try again.'}), 502
    return jsonify({'ok': True, 'reference': reference})


@app.route('/pay/webhook', methods=['POST'])
def pay_webhook():
    """Called by your payment provider. Check their docs: many sign the request, so swap the
    shared-secret check below for their signature check."""
    secret = os.environ.get('PAYMENT_WEBHOOK_SECRET')
    if not secret:
        return jsonify({'error': 'Webhook not configured'}), 503
    if not hmac.compare_digest(request.headers.get('X-Webhook-Secret', ''), secret):
        return jsonify({'error': 'Forbidden'}), 403
    body = json_body()
    if str(body.get('status', '')).lower() != 'success':
        return jsonify({'ok': True})
    conn = db()
    pay = conn.execute('SELECT * FROM payments WHERE reference = ?', (body.get('reference'),)).fetchone()
    done = conn.execute("UPDATE payments SET status = 'paid' WHERE reference = ? AND status = 'pending'",
                        (body.get('reference'),)).rowcount
    conn.commit()
    conn.close()
    if pay and done:  # only the first callback grants access
        grant_days(pay['phone'], SUBSCRIPTION_DAYS)
        # Commission is recorded only after the verified payment callback succeeds.
        # Manual/free admin grants do not create affiliate commissions.
        record_affiliate_payment(pay['phone'], pay['amount'], pay['reference'])
    return jsonify({'ok': True})


@app.route('/api/library')
def api_library():
    """Public catalogue: titles and rows only. No video links."""
    conn = db()
    rows = conn.execute("SELECT id, title, category, upload_date, thumb_key FROM videos WHERE s3_key IS NOT NULL ORDER BY upload_date DESC").fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'title': r['title'], 'category': r['category'] or 'General',
                     'upload_date': r['upload_date'],
                     'thumb': f"/thumb/{r['id']}" if r['thumb_key'] else None} for r in rows])


def presigned(s3_key, seconds=3 * 3600):
    return s3_client.generate_presigned_url(
        'get_object', Params={'Bucket': AWS_BUCKET_NAME, 'Key': s3_key}, ExpiresIn=seconds)


@app.route('/watch/<int:video_id>')
def watch(video_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'login'}), 401
    if not is_subscribed(user):
        return jsonify({'error': 'subscribe'}), 402
    conn = db()
    row = conn.execute('SELECT title, s3_key FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    if not row or not row['s3_key']:
        return jsonify({'error': 'Video not found'}), 404
    return jsonify({'title': row['title'], 'url': presigned(row['s3_key'])})


@app.route('/api/live')
def api_live():
    conn = db()
    row = conn.execute('SELECT title, hls_url, is_live FROM live WHERE id = 1').fetchone()
    conn.close()
    out = {'is_live': bool(row['is_live'] and row['hls_url']), 'title': row['title']}
    if out['is_live'] and is_subscribed(current_user()):
        out['hls_url'] = row['hls_url']
    return jsonify(out)


@app.route('/admin/stream/<int:video_id>')
@requires_admin
def admin_stream(video_id):
    conn = db()
    row = conn.execute('SELECT s3_key FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    if not row or not row['s3_key']:
        return 'Video not found', 404
    return redirect(presigned(row['s3_key'], 900))


@app.route('/admin/live', methods=['GET', 'POST'])
@requires_admin
def admin_live():
    conn = db()
    if request.method == 'POST':
        b = json_body()
        url = (b.get('hls_url') or '').strip()
        on = 1 if b.get('is_live') else 0
        if on and not url.startswith('https://'):
            conn.close()
            return jsonify({'error': 'Paste the https playback link from your live service.'}), 400
        conn.execute('UPDATE live SET title = ?, hls_url = ?, is_live = ? WHERE id = 1',
                     ((b.get('title') or '').strip()[:120] or 'TAWA Live', url, on))
        conn.commit()
    row = conn.execute('SELECT title, hls_url, is_live FROM live WHERE id = 1').fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route('/admin/code', methods=['POST'])
@requires_admin
def admin_code():
    """Make a sign-in code (valid 24 hours) for a number, and optionally add paid days."""
    b = json_body()
    phone = normalize_phone(b.get('phone'))
    if not phone:
        return jsonify({'error': 'Enter a valid Zambian number.'}), 400
    try:
        days = max(0, min(365, int(b.get('days') or 0)))
    except (TypeError, ValueError):
        days = 0
    paid_until = grant_days(phone, days) if days else None
    code = f'{secrets.randbelow(10**6):06d}'
    conn = db()
    conn.execute('INSERT OR REPLACE INTO otps (phone, code_hash, expires, attempts, sent_at) VALUES (?, ?, ?, 0, 0)',
                 (phone, hash_code(phone, code), time.time() + 86400))
    conn.commit()
    conn.close()
    return jsonify({'phone': phone, 'code': code, 'paid_until': paid_until})


@app.route('/admin/grant', methods=['POST'])
@requires_admin
def admin_grant():
    b = json_body()
    phone = normalize_phone(b.get('phone'))
    try:
        days = max(1, min(365, int(b.get('days') or SUBSCRIPTION_DAYS)))
    except (TypeError, ValueError):
        days = SUBSCRIPTION_DAYS
    if not phone:
        return jsonify({'error': 'Enter a valid Zambian number.'}), 400
    return jsonify({'paid_until': grant_days(phone, days)})


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


# ---------------------------------------------------------------------------
# Thumbnails (the picture shown on each video card)
# ---------------------------------------------------------------------------
THUMB_EXTS = {'jpg', 'jpeg', 'png', 'webp'}

def save_thumbnail(file):
    """Upload an image to S3 and return its key (or None if it isn't a valid image)."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in THUMB_EXTS:
        return None
    file.seek(0, os.SEEK_END)
    if file.tell() > 5 * 1024 * 1024:   # 5 MB max
        return None
    file.seek(0)
    key = f"thumbs/{uuid.uuid4().hex[:8]}.{ext}"
    s3_client.upload_fileobj(
        file, AWS_BUCKET_NAME, key,
        ExtraArgs={'ContentType': mimetypes.guess_type(file.filename)[0] or 'image/jpeg'})
    return key


@app.route('/thumb/<int:video_id>')
def thumb(video_id):
    """Public thumbnail. Redirects to a signed S3 link, cached by the browser."""
    conn = db()
    row = conn.execute('SELECT thumb_key FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    if not row or not row['thumb_key']:
        return '', 404
    resp = redirect(presigned(row['thumb_key'], 86400))
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.route('/admin/thumbnail/<int:video_id>', methods=['POST'])
@requires_admin
def admin_thumbnail(video_id):
    key = save_thumbnail(request.files.get('thumbnail'))
    if not key:
        return jsonify({'error': 'Use a JPG, PNG or WEBP image under 5 MB.'}), 400
    conn = db()
    conn.execute('UPDATE videos SET thumb_key = ? WHERE id = ?', (key, video_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


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
            
            # Thumbnail (optional): a failed thumbnail must never fail the video upload
            try:
                thumb_key = save_thumbnail(request.files.get('thumbnail'))
            except Exception as e:
                print("⚠️ Thumbnail upload failed:", str(e))
                thumb_key = None

            # Save to database
            conn = sqlite3.connect('tawa.db')
            c = conn.cursor()
            c.execute("INSERT INTO videos (title, filename, s3_key, category, thumb_key) VALUES (?, ?, ?, ?, ?)",
                     (title, filename, s3_key, category, thumb_key))
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
@requires_admin
def get_videos():
    try:
        conn = sqlite3.connect('tawa.db')
        c = conn.cursor()
        c.execute("SELECT id, title, filename, s3_key, upload_date, category, thumb_key FROM videos ORDER BY upload_date DESC")
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
                'category': video[5] or 'General',  # category at index 5
                'thumb': f"/thumb/{video[0]}" if video[6] else None
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
    subs = 0
    try:
        conn = sqlite3.connect('tawa.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*), COUNT(DISTINCT category) FROM videos")
        total_videos, total_categories = c.fetchone()
        c.execute("SELECT COUNT(*) FROM users WHERE paid_until > ?", (utcnow().isoformat(),))
        subs = c.fetchone()[0]
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
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
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
  .thumb { overflow: hidden; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb-prev { width: 180px; aspect-ratio: 16/9; object-fit: cover; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-2); }
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

  /* ---------- Affiliate management ---------- */
  .aff-form-grid { display:grid; grid-template-columns:1fr 1fr 1fr auto; gap:1rem; align-items:end; margin-bottom:1.5rem; }
  .aff-form-grid .field { min-width:0; margin-bottom:0; }
  .aff-add-wrap .btn { width:100%; white-space:nowrap; }
  .aff-subhead { font-size:1.05rem; margin:1.5rem 0 .8rem; }
  .aff-table { min-width:900px; }
  .aff-table th, .aff-table td { font-size:.88rem; padding:.75rem .65rem; }
  .aff-table code { font-family:var(--mono); font-size:.82rem; word-break:break-all; }
  .aff-message { min-height:1.4rem; margin:-.5rem 0 1rem; color:var(--muted); }
  .aff-message.ok { color:var(--ok); }
  .aff-message.err { color:var(--bad); }
  .aff-actions { display:flex; gap:.35rem; flex-wrap:wrap; }
  .aff-actions .btn-ghost { padding:.4rem .6rem; font-size:.82rem; white-space:nowrap; }
  .aff-status-approved { color:var(--warn); }
  .aff-status-paid { color:var(--ok); }
  .aff-status-void { color:var(--muted); text-decoration:line-through; }
  @media (max-width: 860px) { .aff-form-grid { grid-template-columns:1fr; } .aff-add-wrap .btn { width:auto; } }

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
    <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;justify-content:flex-end">
      <a class="site-link" href="#affiliateManagement">Affiliate management ↓</a>
      <a class="site-link" href="/" target="_blank" rel="noopener">View Main Site →</a>
    </div>
  </div>
</header>

<main class="wrap">
  <div class="page-head">
    <h1>Your catalogue</h1>
    <p>Add new titles to the cloud and check that every one of them streams before your viewers find it.</p>
  </div>

  <section class="card" aria-labelledby="affiliateTitle" id="affiliateManagement">
    <h2 class="card-title" id="affiliateTitle">Affiliate management</h2>
    <p class="card-sub" id="affRule">Each affiliate earns 30% of a customer's first verified subscription payment only. Renewals and free access earn no commission.</p>
    <div id="affMsg" class="aff-message" role="status" aria-live="polite"></div>

    <div class="aff-form-grid">
      <div class="field"><label for="affName">Affiliate name</label><input class="input" id="affName" placeholder="e.g. John Banda" maxlength="60"></div>
      <div class="field"><label for="affPhone">Phone for payouts</label><input class="input" id="affPhone" placeholder="097 123 4567"></div>
      <div class="field"><label for="affCode">Referral code (optional)</label><input class="input" id="affCode" placeholder="Auto-generate"></div>
      <div class="field aff-add-wrap"><label>&nbsp;</label><button class="btn" type="button" id="affAdd">Add affiliate</button></div>
    </div>

    <h3 class="aff-subhead">Affiliates and referrals</h3>
    <div class="table-scroll"><table class="aff-table"><thead><tr><th>Name / phone</th><th>Referral link</th><th>Clicks</th><th>Sign-ups</th><th>Paying</th><th>Owed</th><th>Paid</th><th>Actions</th></tr></thead><tbody id="affRows"><tr><td colspan="8" class="muted-cell">Loading affiliates…</td></tr></tbody></table></div>

    <h3 class="aff-subhead">Assign a customer manually</h3>
    <p class="card-sub">Use this if a customer joined through an affiliate but the referral link was not saved. Assign before the customer pays.</p>
    <div class="aff-form-grid aff-assign-grid">
      <div class="field"><label for="affCustomerPhone">Customer phone</label><input class="input" id="affCustomerPhone" placeholder="097 123 4567"></div>
      <div class="field"><label for="affAssignCode">Affiliate code</label><input class="input" id="affAssignCode" placeholder="JOHN42"></div>
      <div class="field aff-add-wrap"><label>&nbsp;</label><button class="btn" type="button" id="affAssign">Assign referral</button></div>
    </div>

    <h3 class="aff-subhead">Recent commissions</h3>
    <div class="table-scroll"><table class="aff-table"><thead><tr><th>Date</th><th>Code</th><th>Customer phone</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody id="affCommissionRows"><tr><td colspan="6" class="muted-cell">Loading commissions…</td></tr></tbody></table></div>
    <p class="card-sub" style="margin-top:1rem;margin-bottom:0">Only verified payment callbacks create commissions. Giving someone free access with the admin tools does not earn a commission. Mark a payout as paid only after you have sent the money.</p>
  </section>


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
      <div class="stat-label">Active Subscribers</div>
      <div class="stat-value">{{ subs }}</div>
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

          <div class="field" style="margin-top:1.2rem">
            <label>Thumbnail (the picture people see)</label>
            <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
              <img class="thumb-prev" id="thumbPrev" alt="Thumbnail preview">
              <div style="display:flex;flex-direction:column;gap:.5rem;align-items:flex-start">
                <button type="button" class="btn-ghost" id="thumbNewFrame">Pick another frame</button>
                <button type="button" class="btn-ghost" id="thumbOwn">Upload my own image</button>
                <input type="file" id="thumbFile" accept="image/jpeg,image/png,image/webp" hidden>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn" id="uploadBtn">Upload to cloud</button>
      </div>
    </form>
  </section>

  <section class="card" aria-labelledby="liveHead">
    <h2 class="card-title" id="liveHead">Live and access</h2>
    <p class="card-sub">Paste the playback link (.m3u8) from your live streaming service, then go live. Subscribers see it in the Live now row.</p>
    <div class="upload-grid">
      <div>
        <div class="field"><label for="liveTitle">Live title</label><input class="input" id="liveTitle" maxlength="120" placeholder="e.g. Friday night match"></div>
        <div class="field"><label for="liveUrl">Playback link</label><input class="input" id="liveUrl" placeholder="https://.../playlist.m3u8"></div>
        <div style="display:flex;gap:0.6rem;align-items:center"><button class="btn" type="button" id="goLive">Go live</button><button class="btn-ghost" type="button" id="endLive">End live</button><span id="liveState" style="color:var(--muted)"></span></div>
      </div>
      <div>
        <div class="field"><label for="grantPhone">Add a viewer (they paid you by mobile money)</label><input class="input" id="grantPhone" placeholder="097 123 4567"></div>
        <div class="field"><label for="grantDays">Days</label><input class="input" id="grantDays" type="number" value="30" min="1" max="365"></div>
        <button class="btn" type="button" id="grantBtn">Give access and make code</button>
        <div id="codeOut" style="display:none;margin-top:1rem;padding:1rem;border:1px solid var(--line);border-radius:10px;background:var(--bg)">
          <div id="codeText" style="font-size:.95rem;margin-bottom:.7rem"></div>
          <button class="btn-ghost" type="button" id="copyCode">Copy message</button>
        </div>
      </div>
    </div>
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
    startThumb(file);
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

  /* ---------- Thumbnails ---------- */
  let thumbBlob = null, thumbVid = null, prevUrl = null;
  function clearThumb() {
    thumbBlob = null;
    if (thumbVid) { URL.revokeObjectURL(thumbVid.src); thumbVid = null; }
    if (prevUrl) { URL.revokeObjectURL(prevUrl); prevUrl = null; }
    $('thumbPrev').removeAttribute('src');
  }
  function showThumb(blob) {
    thumbBlob = blob;
    if (prevUrl) URL.revokeObjectURL(prevUrl);
    prevUrl = URL.createObjectURL(blob);
    $('thumbPrev').src = prevUrl;
  }
  function captureFrame(fraction) {
    const v = thumbVid; if (!v) return;
    v.onseeked = () => {
      v.onseeked = null;
      const c = document.createElement('canvas'); c.width = 640; c.height = 360;
      const vr = v.videoWidth / v.videoHeight, cr = 16 / 9;
      let sw = v.videoWidth, sh = v.videoHeight, sx = 0, sy = 0;
      if (vr > cr) { sw = sh * cr; sx = (v.videoWidth - sw) / 2; } else { sh = sw / cr; sy = (v.videoHeight - sh) / 2; }
      c.getContext('2d').drawImage(v, sx, sy, sw, sh, 0, 0, 640, 360);
      c.toBlob((b) => { if (b) showThumb(b); }, 'image/jpeg', 0.85);
    };
    v.currentTime = Math.max(0.5, (v.duration || 2) * fraction);
  }
  function startThumb(file) {
    clearThumb();
    const v = document.createElement('video');
    v.muted = true; v.preload = 'auto'; v.playsInline = true;
    v.src = URL.createObjectURL(file);
    v.onloadedmetadata = () => captureFrame(0.1);
    v.onerror = () => setStatus('error', 'Cannot preview this format', 'Press "Upload my own image" to add a thumbnail.');
    thumbVid = v;
  }
  $('thumbNewFrame').addEventListener('click', () => captureFrame(0.1 + Math.random() * 0.7));
  $('thumbOwn').addEventListener('click', () => $('thumbFile').click());
  $('thumbFile').addEventListener('change', (e) => { if (e.target.files[0]) showThumb(e.target.files[0]); });

  /* ---------- Upload (XHR so a big video shows real progress) ---------- */
  function resetForm() {
    $('uploadForm').reset();
    chosenFile = null;
    clearThumb();
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
    if (thumbBlob) data.append('thumbnail', thumbBlob, thumbBlob.name || 'thumb.jpg');

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
      if (v.thumb) { thumb.textContent = ''; const im = document.createElement('img'); im.src = v.thumb; im.alt = ''; thumb.appendChild(im); }
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
      const acts = document.createElement('div');
      acts.style.cssText = 'display:flex;gap:.5rem;justify-content:flex-end;flex-wrap:wrap';
      if (v.s3_url) {
        const a = document.createElement('a');
        a.className = 'test-link'; a.href = '/admin/stream/' + v.id; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Test Stream ↗'; acts.appendChild(a);
      } else {
        const s = document.createElement('span'); s.className = 'muted-cell'; s.textContent = 'No cloud file'; acts.appendChild(s);
      }
      const tb = document.createElement('button');
      tb.type = 'button'; tb.className = 'btn-ghost'; tb.textContent = v.thumb ? 'Change thumbnail' : 'Add thumbnail';
      const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/jpeg,image/png,image/webp'; inp.hidden = true;
      tb.onclick = () => inp.click();
      inp.onchange = async () => {
        if (!inp.files[0]) return;
        const fd = new FormData(); fd.append('thumbnail', inp.files[0]);
        tb.disabled = true; tb.textContent = 'Saving…';
        const r = await fetch('/admin/thumbnail/' + v.id, { method: 'POST', body: fd });
        if (!r.ok) { const d = await r.json().catch(() => ({})); notify('error', 'Thumbnail failed', d.error || 'Try again.'); }
        loadLibrary();
      };
      acts.append(tb, inp);
      tr.appendChild(cell(acts, 'right'));

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

  /* ---------- Live and access ---------- */
  function notify(kind, title, text) { setStatus(kind, title, text); $('statusCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  async function postJSON(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let d = {};
    try { d = await r.json(); } catch (e) { /* non-JSON */ }
    if (!r.ok) throw new Error(d.error || 'Request failed');
    return d;
  }
  async function loadLive() {
    try {
      const d = await (await fetch('/admin/live')).json();
      $('liveTitle').value = d.title || '';
      $('liveUrl').value = d.hls_url || '';
      $('liveState').textContent = d.is_live ? 'You are live' : 'Not live';
    } catch (e) { /* leave blank */ }
  }
  async function setLive(on) {
    try {
      await postJSON('/admin/live', { title: $('liveTitle').value, hls_url: $('liveUrl').value, is_live: on });
      notify('success', on ? 'You are live' : 'Live ended', on ? 'Subscribers now see it in the Live now row.' : 'The Live now row is hidden.');
      loadLive();
    } catch (e) { notify('error', 'Could not update live', e.message); }
  }
  $('goLive').addEventListener('click', () => setLive(true));
  $('endLive').addEventListener('click', () => setLive(false));
  $('grantBtn').addEventListener('click', async () => {
    try {
      const d = await postJSON('/admin/code', { phone: $('grantPhone').value, days: $('grantDays').value });
      const msg = 'Your TAWA sign-in code is ' + d.code + '. Go to ' + location.origin + ', tap Sign in, enter your number ' + d.phone + ' and then this code.';
      $('codeText').textContent = msg;
      $('codeOut').style.display = 'block';
      notify('success', 'Ready to send', 'Copy the message below and send it to ' + d.phone + (d.paid_until ? '. Access until ' + d.paid_until.slice(0, 10) + '.' : '.'));
    } catch (e) { notify('error', 'Could not make the code', e.message); }
  });
  $('copyCode').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('codeText').textContent); $('copyCode').textContent = 'Copied'; } catch (e) { $('copyCode').textContent = 'Select the text and copy it'; }
    setTimeout(() => { $('copyCode').textContent = 'Copy message'; }, 2000);
  });
  /* ---------- Affiliate management ---------- */
  const moneyK = (ngwee) => 'K' + (Number(ngwee || 0) / 100).toFixed(2);
  function affMessage(message, kind) {
    const el = $('affMsg'); el.textContent = message || ''; el.className = 'aff-message' + (kind ? ' ' + kind : '');
  }
  async function affPost(url, body) {
    const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Affiliate request failed.');
    return data;
  }
  function affCell(row, value, className) {
    const td = document.createElement('td'); if (className) td.className = className;
    if (value instanceof Node) td.appendChild(value); else td.textContent = value == null ? '' : String(value);
    row.appendChild(td); return td;
  }
  function affButton(label, handler, disabled) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn-ghost'; b.textContent = label; b.disabled = !!disabled;
    b.addEventListener('click', async () => { b.disabled = true; try { await handler(); } catch (e) { affMessage(e.message, 'err'); } finally { b.disabled = false; } });
    return b;
  }
  async function loadAffiliates() {
    try {
      const response = await fetch('/admin/affiliates/data', {cache:'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Could not load affiliates.');
      $('affRule').textContent = 'Commission: ' + Math.round(data.rate * 100) + '% of the first verified subscription payment. At K' + data.price + ', that is ' + moneyK(Math.round(data.price * 100 * data.rate)) + ' per qualifying customer. One commission per customer; renewals and free access earn nothing.';
      const rows = $('affRows'); rows.textContent = '';
      if (!data.affiliates.length) { const tr = document.createElement('tr'); affCell(tr, 'No affiliates yet. Add the first one above.', 'muted-cell').colSpan = 8; rows.appendChild(tr); }
      data.affiliates.forEach((a) => {
        const tr = document.createElement('tr');
        affCell(tr, a.name + ' · ' + a.phone);
        const linkCell = document.createElement('td');
        const code = document.createElement('code'); code.textContent = location.origin + '/r/' + a.code; linkCell.appendChild(code); linkCell.appendChild(document.createTextNode(' '));
        linkCell.appendChild(affButton('Copy', async () => { const link = location.origin + '/r/' + a.code; try { await navigator.clipboard.writeText(link); affMessage('Referral link copied for ' + a.name + '.', 'ok'); } catch (_) { window.prompt('Copy this referral link', link); } })); tr.appendChild(linkCell);
        [a.clicks, a.signups, a.customers].forEach(n => affCell(tr, n));
        affCell(tr, moneyK(a.owed)); affCell(tr, moneyK(a.paid));
        const actions = document.createElement('td'); const wrap = document.createElement('div'); wrap.className = 'aff-actions';
        wrap.appendChild(affButton('Pay ' + moneyK(a.owed), async () => {
          if (!a.owed) return;
          if (!confirm('Have you already sent ' + moneyK(a.owed) + ' to ' + a.name + '? Only confirm after payment.')) return;
          const result = await affPost('/admin/affiliates/payout', {code:a.code});
          affMessage('Marked ' + moneyK(a.owed) + ' as paid (' + result.paid + ' commission(s)).', 'ok'); await loadAffiliates();
        }, !a.owed));
        wrap.appendChild(affButton(a.active ? 'Pause' : 'Resume', async () => { await affPost('/admin/affiliates/toggle', {code:a.code}); affMessage(a.active ? 'Affiliate paused.' : 'Affiliate resumed.', 'ok'); await loadAffiliates(); }));
        actions.appendChild(wrap); tr.appendChild(actions); rows.appendChild(tr);
      });
      const commissions = $('affCommissionRows'); commissions.textContent = '';
      if (!data.commissions.length) { const tr = document.createElement('tr'); affCell(tr, 'No commissions yet. They appear after a verified subscription payment.', 'muted-cell').colSpan = 6; commissions.appendChild(tr); }
      data.commissions.forEach((c) => {
        const tr = document.createElement('tr'); affCell(tr, (c.created_at || '').slice(0,10)); affCell(tr, c.code); affCell(tr, c.customer_phone); affCell(tr, moneyK(c.amount_ngwee));
        const status = document.createElement('span'); status.textContent = c.status + (c.paid_at ? ' · ' + c.paid_at.slice(0,10) : ''); status.className = c.status === 'paid' ? 'aff-status-paid' : (c.status === 'void' ? 'aff-status-void' : 'aff-status-approved'); affCell(tr, status);
        const actionCell = document.createElement('td');
        if (c.status === 'approved') actionCell.appendChild(affButton('Void', async () => { if (!confirm('Void this commission? Use this only for an invalid commission.')) return; await affPost('/admin/affiliates/void', {id:c.id}); affMessage('Commission voided.', 'ok'); await loadAffiliates(); }));
        tr.appendChild(actionCell); commissions.appendChild(tr);
      });
    } catch (e) { affMessage(e.message + ' Refresh the admin page after the affiliate backend is deployed.', 'err'); }
  }
  $('affAdd').addEventListener('click', async () => {
    try { const result = await affPost('/admin/affiliates/add', {name:$('affName').value, phone:$('affPhone').value, code:$('affCode').value});
      affMessage('Affiliate added. Referral link: ' + location.origin + '/r/' + result.code, 'ok');
      $('affName').value = $('affPhone').value = $('affCode').value = ''; await loadAffiliates();
    } catch (e) { affMessage(e.message, 'err'); }
  });
  $('affAssign').addEventListener('click', async () => {
    try { await affPost('/admin/affiliates/assign', {phone:$('affCustomerPhone').value, code:$('affAssignCode').value});
      affMessage('Customer referral assigned.', 'ok'); $('affCustomerPhone').value = $('affAssignCode').value = ''; await loadAffiliates();
    } catch (e) { affMessage(e.message, 'err'); }
  });
  loadAffiliates();

  loadLive();

  $('search').addEventListener('input', renderLibrary);
  $('refresh').addEventListener('click', loadLibrary);
  document.addEventListener('DOMContentLoaded', loadLibrary);
</script>
</body>
</html>
''', total_videos=total_videos, total_categories=total_categories, subs=subs)

# Affiliate system: referral links, admin dashboard, and payment-confirmed commissions.
from affiliates import init_affiliates
record_affiliate_payment = init_affiliates(app, db, requires_admin, normalize_phone, json_body, current_user)


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
