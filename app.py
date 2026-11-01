import os
import re
import time
import uuid
import hmac
import hashlib
import secrets
import datetime
import mimetypes
import base64
from functools import wraps

import boto3
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, Response, session, redirect
from pgcompat import sqlite3
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

app = Flask(__name__)

# S3-compatible object storage (Backblaze B2).
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME', 'tawa-streaming')
AWS_REGION = os.environ.get('AWS_REGION', 'eu-central-003')
S3_ENDPOINT_URL = (
    os.environ.get('B2_ENDPOINT_URL')
    or os.environ.get('AWS_ENDPOINT_URL')
    or 'https://backblazeb2.com'
).rstrip('/')

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION,
)

# MTN MoMo Credentials (Safely configured to pull from Render Variables)
MOMO_PRIMARY_KEY = os.environ.get('MOMO_PRIMARY_KEY', '6f1febfcbb654d3a88fba810d1fd1deb')
MOMO_USER_UUID = os.environ.get('MOMO_USER_UUID', 'a9e2b104-c518-47bc-ad74-88899dfc4491')
MOMO_API_KEY = os.environ.get('MOMO_API_KEY', '2514135a636d47309eadb7284eb5ac10')

# ---------------------------------------------------------------------------
# Admin protection
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
    """Add missing columns to existing database safely checking column tuple index"""
    conn = sqlite3.connect('tawa.db')
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(videos)")
        columns = [column[1] for column in c.fetchall()]  # Pull out the text names explicitly
        
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         title TEXT NOT NULL,
         filename TEXT NOT NULL,
         upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    
    c.execute("PRAGMA table_info(videos)")
    columns = [column[1] for column in c.fetchall()]  # Fixed: tuple mapping to locate text item names
    
    if 's3_key' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN s3_key TEXT")
    if 'category' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN category TEXT DEFAULT 'General'")
    if 'thumb_key' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN thumb_key TEXT")
    if 'views' not in columns:
        c.execute("ALTER TABLE videos ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
        
    conn.commit()
    conn.close()

# Execute database checks
init_db()
fix_database()

# ---------------------------------------------------------------------------
# Accounts (phone number + SMS code), K15 subscription, and live
# ---------------------------------------------------------------------------
PRICE_KWACHA = 15
SUBSCRIPTION_DAYS = 30

app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('DEV_MODE') != '1',
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
    return request.get_json(silent=True) or {}


def normalize_phone(raw):
    digits = re.sub(r'[\s\-()]', '', raw or '')
    m = re.fullmatch(r'(?:\+?260|0)?(\d{9})', digits)
    return '+260' + m.group(1) if m else None


def hash_code(phone, code):
    return hashlib.sha256(f'{app.secret_key}:{phone}:{code}'.encode()).hexdigest()


def send_sms(phone, text):
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
        r = requests.post('https://africastalking.com',
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
    conn = db()
    conn.execute('INSERT OR IGNORE INTO users (phone) VALUES (?)', (phone,))
    row = conn.execute('SELECT paid_until FROM users WHERE phone = ?', (phone,)).fetchone()
    base = utcnow()
    if row and row['paid_until']:
        try:
            base = max(base, datetime.datetime.fromisoformat(row['paid_until']))
        except Exception:
            pass
    new_until = (base + datetime.timedelta(days=days)).isoformat()
    conn.execute('UPDATE users SET paid_until = ? WHERE phone = ?', (new_until, phone))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MTN Mobile Money Engine Integration
# ---------------------------------------------------------------------------
def get_momo_access_token():
    """Generates an API bearer token using standard Basic authentication configuration"""
    url = "https://mtn.com"
    auth_str = f"{MOMO_USER_UUID}:{MOMO_API_KEY}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Ocp-Apim-Subscription-Key": MOMO_PRIMARY_KEY,
        "Authorization": f"Basic {b64_auth}"
    }
    try:
        r = requests.post(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json().get("access_token")
    except requests.RequestException as e:
        print("MoMo Authentication Exception:", e)
    return None


@app.route('/api/pay/momo', methods=['POST'])
def trigger_momo_payment():
    """Initiates an asynchronous requesttopay collect prompt to user phone"""
    user = current_user()
    if not user:
        return jsonify({'error': 'Unauthorized session'}), 401

    phone = user['phone']
    clean_phone = re.sub(r'\D', '', phone) # strips symbols to standard format (ex: 260961234567)

    token = get_momo_access_token()
    if not token:
        return jsonify({'error': 'Internal authentication connection error'}), 500

    url = "https://mtn.com"
    transaction_uuid = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Reference-Id": transaction_uuid,
        "X-Target-Environment": "sandbox",
        "Ocp-Apim-Subscription-Key": MOMO_PRIMARY_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "amount": str(PRICE_KWACHA),
