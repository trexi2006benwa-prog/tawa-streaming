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
    clean_phone = re.sub(r'\D', '', phone)

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
        "currency": "EUR",
        "externalId": str(int(time.time())),
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": clean_phone
        },
        }
    }

    # The payment request is intentionally not sent until the correct MTN
    # Zambia API base URL and credentials are configured in Render.
    return jsonify({
        'error': 'MTN payment setup is incomplete. Please try again later.'
    }), 503
