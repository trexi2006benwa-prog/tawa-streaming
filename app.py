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

# S3-compatible object storage (Backblaze B2).
# Set these in Render > Environment. Keep the existing AWS_* key names if
# those are the names already used by your deployment.
AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME', 'tawa-streaming')
AWS_REGION = os.environ.get('AWS_REGION', 'eu-central-003')
S3_ENDPOINT_URL = (
    os.environ.get('B2_ENDPOINT_URL')
    or os.environ.get('AWS_ENDPOINT_URL')
    or 'https://s3.eu-central-003.backblazeb2.com'
).rstrip('/')

# Boto3 must be pointed at the Backblaze endpoint; otherwise it calls AWS S3.
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION,
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
