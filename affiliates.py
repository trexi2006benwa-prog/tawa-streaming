"""TAWA affiliate system.

Rules:
- An affiliate earns 30% of a customer's FIRST verified subscription payment.
- One commission per customer. Renewals never create another one.
- Commission is approved automatically the moment access is granted for a payment
  (admin "Give access" or, later, the payment webhook). Void it for free access.
- Payouts are manual: you send the money, then press "Mark as paid".

Hook it up at the bottom of app.py, above `if __name__ == '__main__':`
    from affiliates import init_affiliates
    init_affiliates(app, db, requires_admin, normalize_phone, json_body, current_user)
"""
import re
import sys
import secrets
import datetime
import os

from flask import g, jsonify, redirect, request, Response

COMMISSION_RATE = 0.30
COOKIE = 'tawa_ref'
COOKIE_DAYS = 30
BOTS = ('bot', 'whatsapp', 'facebookexternalhit', 'preview', 'crawler')


def init_affiliates(app, db, requires_admin, normalize_phone, json_body, current_user):
    mod = sys.modules[app.import_name]  # the app module, so we can watch grant_days

    conn = db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS affiliates (
            code TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
            active INTEGER DEFAULT 1, clicks INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS referrals (
            customer_phone TEXT PRIMARY KEY, code TEXT NOT NULL,
            attached_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL,
            customer_phone TEXT NOT NULL, price_ngwee INTEGER NOT NULL,
            amount_ngwee INTEGER NOT NULL, status TEXT DEFAULT 'approved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, paid_at TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_commission_per_customer
            ON commissions (customer_phone) WHERE status <> 'void';
        CREATE UNIQUE INDEX IF NOT EXISTS one_commission_per_customer_all
            ON commissions (customer_phone)
    ''')
    conn.commit()
    conn.close()

    def now():
        return datetime.datetime.utcnow().isoformat()

    # ---- 1. Someone opens an affiliate link -------------------------------
    @app.route('/r/<code>')
    def aff_click(code):
        code = code.upper()[:20]
        resp = redirect('/')
        conn = db()
        row = conn.execute('SELECT code FROM affiliates WHERE code = ? AND active = 1', (code,)).fetchone()
        if row and not request.cookies.get(COOKIE):   # first affiliate link wins
            ua = (request.headers.get('User-Agent') or '').lower()
            if not any(b in ua for b in BOTS):
                conn.execute('UPDATE affiliates SET clicks = clicks + 1 WHERE code = ?', (code,))
                conn.commit()
            resp.set_cookie(COOKIE, code, max_age=COOKIE_DAYS * 86400, httponly=True,
                            samesite='Lax', secure=not os.environ.get('DEV_MODE'))
        conn.close()
        return resp

    # ---- 2. The visitor signs in: attach the code to their account, once --
    @app.before_request
    def aff_attach():
        code = request.cookies.get(COOKIE)
        if not code or not request.cookies.get('session'):
            return
        user = current_user()
        if not user:
            return
        g.clear_ref = True
        if user['paid_until']:        # only people who have never paid can be referred
            return
        conn = db()
        aff = conn.execute('SELECT phone, active FROM affiliates WHERE code = ?', (code,)).fetchone()
        if aff and aff['active'] and aff['phone'] != user['phone']:   # no earning from yourself
            conn.execute('INSERT INTO referrals (customer_phone, code) VALUES (?, ?) ON CONFLICT DO NOTHING',
                         (user['phone'], code))
            conn.commit()
        conn.close()

    @app.after_request
    def aff_cookie_cleanup(resp):
        if g.get('clear_ref'):
            resp.delete_cookie(COOKIE)
        return resp

    # ---- 3. A payment is verified: create the commission (first one only) --
    def make_commission(phone, paid_amount=None, payment_reference=None):
        conn = db()
        try:
            ref = conn.execute('SELECT code FROM referrals WHERE customer_phone = ?', (phone,)).fetchone()
            if not ref:
                return
            aff = conn.execute('SELECT phone, active FROM affiliates WHERE code = ?', (ref['code'],)).fetchone()
            if not aff or not aff['active'] or aff['phone'] == phone:
                return
            paid_amount = mod.PRICE_KWACHA if paid_amount is None else float(paid_amount)
            if paid_amount <= 0:
                return
            price = int(round(paid_amount * 100))
            amount = int(round(price * COMMISSION_RATE))
            conn.execute(
                "INSERT OR IGNORE INTO commissions (code, customer_phone, price_ngwee, amount_ngwee) VALUES (?, ?, ?, ?)",
                (ref['code'], phone, price, amount))
            conn.commit()
        except Exception as e:   # a commission problem must never block someone's access
            print('Affiliate commission error:', e)
        finally:
            conn.close()

    # IMPORTANT: do not hook grant_days. Admin/free access must never earn commission.
    # The app calls this function only after a verified payment callback succeeds.

    # ---- Admin ------------------------------------------------------------
    @app.route('/admin/affiliates/data')
    @requires_admin
    def aff_data():
        conn = db()
        affs = conn.execute('''
            SELECT a.code, a.name, a.phone, a.active, a.clicks,
              (SELECT COUNT(*) FROM referrals r WHERE r.code = a.code) AS signups,
              (SELECT COUNT(*) FROM commissions c WHERE c.code = a.code AND c.status <> 'void') AS customers,
              (SELECT COALESCE(SUM(amount_ngwee), 0) FROM commissions c WHERE c.code = a.code AND c.status = 'approved') AS owed,
              (SELECT COALESCE(SUM(amount_ngwee), 0) FROM commissions c WHERE c.code = a.code AND c.status = 'paid') AS paid
            FROM affiliates a ORDER BY a.created_at DESC''').fetchall()
        coms = conn.execute('''SELECT id, code, customer_phone, amount_ngwee, status, created_at, paid_at
                               FROM commissions ORDER BY id DESC LIMIT 100''').fetchall()
        conn.close()
        return jsonify({'affiliates': [dict(r) for r in affs], 'commissions': [dict(r) for r in coms],
                        'price': mod.PRICE_KWACHA, 'rate': COMMISSION_RATE})

    @app.route('/admin/affiliates/add', methods=['POST'])
    @requires_admin
    def aff_add():
        b = json_body()
        name = (b.get('name') or '').strip()[:60]
        phone = normalize_phone(b.get('phone'))
        if not name or not phone:
            return jsonify({'error': 'Enter a name and a valid Zambian phone number.'}), 400
        conn = db()
        code = re.sub(r'[^A-Z0-9]', '', (b.get('code') or '').upper())[:20]
        if code and len(code) < 3:
            conn.close()
            return jsonify({'error': 'A custom code needs at least 3 letters or numbers.'}), 400
        if not code:
            base = re.sub(r'[^A-Z]', '', name.upper())[:6] or 'AFF'
            for _ in range(60):
                code = base + str(secrets.randbelow(90) + 10)
                if not conn.execute('SELECT 1 FROM affiliates WHERE code = ?', (code,)).fetchone():
                    break
        if conn.execute('SELECT 1 FROM affiliates WHERE code = ?', (code,)).fetchone():
            conn.close()
            return jsonify({'error': 'That code is taken. Try another.'}), 400
        conn.execute('INSERT INTO affiliates (code, name, phone) VALUES (?, ?, ?)', (code, name, phone))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'code': code})

    @app.route('/admin/affiliates/toggle', methods=['POST'])
    @requires_admin
    def aff_toggle():
        conn = db()
        conn.execute('UPDATE affiliates SET active = 1 - active WHERE code = ?', ((json_body().get('code') or ''),))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.route('/admin/affiliates/assign', methods=['POST'])
    @requires_admin
    def aff_assign():
        b = json_body()
        phone = normalize_phone(b.get('phone'))
        code = (b.get('code') or '').strip().upper()
        if not phone:
            return jsonify({'error': 'Enter the customer\'s Zambian phone number.'}), 400
        conn = db()
        aff = conn.execute('SELECT phone FROM affiliates WHERE code = ?', (code,)).fetchone()
        have = conn.execute('SELECT code FROM referrals WHERE customer_phone = ?', (phone,)).fetchone()
        if not aff:
            conn.close()
            return jsonify({'error': 'No affiliate has that code.'}), 400
        if aff['phone'] == phone:
            conn.close()
            return jsonify({'error': 'An affiliate cannot earn from their own number.'}), 400
        if have:
            conn.close()
            return jsonify({'error': 'That customer already belongs to ' + have['code'] + '.'}), 400
        conn.execute('INSERT INTO referrals (customer_phone, code) VALUES (?, ?)', (phone, code))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.route('/admin/affiliates/payout', methods=['POST'])
    @requires_admin
    def aff_payout():
        conn = db()
        n = conn.execute("UPDATE commissions SET status = 'paid', paid_at = ? WHERE code = ? AND status = 'approved'",
                         (now(), (json_body().get('code') or ''))).rowcount
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'paid': n})

    @app.route('/admin/affiliates/void', methods=['POST'])
    @requires_admin
    def aff_void():
        conn = db()
        conn.execute("UPDATE commissions SET status = 'void' WHERE id = ? AND status = 'approved'",
                     (int(json_body().get('id') or 0),))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.route('/admin/affiliates')
    @requires_admin
    def aff_page():
        return Response(PAGE, mimetype='text/html')

    return make_commission


PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow"><title>TAWA Affiliates</title>
<style>
  :root { --bg:#0F172A; --panel:#1E293B; --line:#2B3A52; --text:#F1F5F9; --muted:#94A3B8; --sky:#38BDF8; --ok:#34D399; --bad:#F87171; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; line-height:1.5; padding:1.5rem clamp(1rem,4vw,3rem) 4rem; }
  a { color:var(--sky); } h1 { font-size:2rem; } h2 { font-size:1.2rem; margin-bottom:.8rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:1.3rem; margin-top:1.2rem; }
  .muted { color:var(--muted); font-size:.92rem; }
  .row { display:flex; gap:.6rem; flex-wrap:wrap; align-items:end; }
  label { display:block; font-size:.85rem; color:var(--muted); margin-bottom:.25rem; }
  input { height:42px; padding:0 .8rem; border-radius:10px; border:1px solid var(--line); background:var(--bg); color:var(--text); font-size:.95rem; }
  button { height:42px; padding:0 1.1rem; border:none; border-radius:10px; background:var(--sky); color:#06243A; font-weight:700; cursor:pointer; }
  button.g { background:transparent; color:var(--text); border:1px solid var(--line); height:34px; padding:0 .8rem; font-weight:500; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .scroll { overflow-x:auto; } table { width:100%; border-collapse:collapse; min-width:760px; }
  th, td { text-align:left; padding:.7rem .6rem; border-bottom:1px solid var(--line); font-size:.92rem; }
  th { color:var(--muted); font-weight:500; } td.r, th.r { text-align:right; }
  code { background:var(--bg); padding:.15rem .5rem; border-radius:6px; }
  .tag { padding:.15rem .6rem; border-radius:999px; font-size:.8rem; border:1px solid var(--line); }
  .approved { color:#FCD34D; } .paid { color:var(--ok); } .void { color:var(--muted); text-decoration:line-through; }
  #msg { margin-top:1rem; min-height:1.4rem; } .err { color:var(--bad); } .okk { color:var(--ok); }
</style></head><body>
<a href="/admin">&larr; Back to admin</a>
<h1>Affiliates</h1>
<p class="muted" id="rule">Loading…</p>
<div id="msg" role="status"></div>

<div class="card"><h2>Add an affiliate</h2>
  <div class="row">
    <div><label for="n">Name</label><input id="n" placeholder="e.g. John Banda"></div>
    <div><label for="p">Phone (for payouts)</label><input id="p" placeholder="097 123 4567"></div>
    <div><label for="c">Code (optional)</label><input id="c" placeholder="auto"></div>
    <button id="add">Add affiliate</button>
  </div>
</div>

<div class="card"><h2>Affiliates</h2><div class="scroll"><table>
  <thead><tr><th>Name</th><th>Link</th><th class="r">Clicks</th><th class="r">Sign-ups</th><th class="r">Paying</th><th class="r">Owed</th><th class="r">Paid</th><th></th></tr></thead>
  <tbody id="aff"></tbody></table></div>
  <p class="muted" style="margin-top:.8rem">Clicks can be inflated by chat previews. Trust sign-ups and paying customers.</p>
</div>

<div class="card"><h2>Assign a customer by hand</h2>
  <p class="muted" style="margin-bottom:.8rem">For someone who joined through an affiliate but whose link did not carry over. Only works before they have paid.</p>
  <div class="row">
    <div><label for="ap">Customer phone</label><input id="ap" placeholder="097 123 4567"></div>
    <div><label for="ac">Affiliate code</label><input id="ac" placeholder="JOHN42"></div>
    <button id="assign">Assign</button>
  </div>
</div>

<div class="card"><h2>Commissions</h2><div class="scroll"><table>
  <thead><tr><th>Date</th><th>Affiliate</th><th>Customer</th><th class="r">Amount</th><th>Status</th><th></th></tr></thead>
  <tbody id="com"></tbody></table></div>
  <p class="muted" style="margin-top:.8rem">Giving access in admin counts as a verified payment. If you gave free access by mistake, press Void.</p>
</div>

<script>
  const $ = (id) => document.getElementById(id);
  const K = (n) => 'K' + (n / 100).toFixed(2);
  const el = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
  function say(t, ok) { $('msg').textContent = t || ''; $('msg').className = ok ? 'okk' : 'err'; }
  async function post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Something went wrong.');
    return d;
  }
  function td(child, cls) { const t = document.createElement('td'); if (cls) t.className = cls; if (child !== undefined) t.append(child); return t; }
  async function load() {
    const d = await (await fetch('/admin/affiliates/data')).json();
    $('rule').textContent = 'Each affiliate earns ' + Math.round(d.rate * 100) + '% of a customer\u2019s first verified payment (K' + d.price + ' plan = ' + K(Math.round(d.price * 100 * d.rate)) + '), once per customer. Renewals earn nothing.';
    const a = $('aff'); a.textContent = '';
    if (!d.affiliates.length) { const tr = el('tr'); const c = td('No affiliates yet.'); c.colSpan = 8; c.className = 'muted'; tr.append(c); a.append(tr); }
    d.affiliates.forEach((x) => {
      const tr = el('tr');
      tr.append(td(x.name + ' \u00b7 ' + x.phone));
      const link = location.origin + '/r/' + x.code;
      const cell = td(); cell.append(el('code', '', x.code), ' ');
      const cp = el('button', 'g', 'Copy link'); cp.onclick = async () => { try { await navigator.clipboard.writeText(link); cp.textContent = 'Copied'; } catch (e) { prompt('Copy this link', link); } setTimeout(() => { cp.textContent = 'Copy link'; }, 1500); };
      cell.append(cp); tr.append(cell);
      [x.clicks, x.signups, x.customers].forEach((n) => tr.append(td(String(n), 'r')));
      tr.append(td(K(x.owed), 'r'), td(K(x.paid), 'r'));
      const act = td(); act.className = 'r';
      const pay = el('button', 'g', 'Mark ' + K(x.owed) + ' as paid'); pay.disabled = x.owed === 0;
      pay.onclick = async () => { if (confirm('Mark ' + K(x.owed) + ' as paid to ' + x.name + '? Only do this after you have sent the money.')) { await post('/admin/affiliates/payout', { code: x.code }); say('Marked as paid.', true); load(); } };
      const tg = el('button', 'g', x.active ? 'Pause' : 'Resume'); tg.style.marginLeft = '.4rem';
      tg.onclick = async () => { await post('/admin/affiliates/toggle', { code: x.code }); load(); };
      act.append(pay, tg); tr.append(act); a.append(tr);
    });
    const c = $('com'); c.textContent = '';
    if (!d.commissions.length) { const tr = el('tr'); const t = td('No commissions yet.'); t.colSpan = 6; t.className = 'muted'; tr.append(t); c.append(tr); }
    d.commissions.forEach((x) => {
      const tr = el('tr');
      tr.append(td((x.created_at || '').slice(0, 10)), td(x.code), td(x.customer_phone), td(K(x.amount_ngwee), 'r'));
      tr.append(td(el('span', 'tag ' + x.status, x.status + (x.paid_at ? ' ' + x.paid_at.slice(0, 10) : ''))));
      const t = td(); t.className = 'r';
      if (x.status === 'approved') { const v = el('button', 'g', 'Void'); v.onclick = async () => { if (confirm('Void this commission?')) { await post('/admin/affiliates/void', { id: x.id }); load(); } }; t.append(v); }
      tr.append(t); c.append(tr);
    });
  }
  $('add').onclick = async () => { try { const r = await post('/admin/affiliates/add', { name: $('n').value, phone: $('p').value, code: $('c').value }); say('Added. Their link is ' + location.origin + '/r/' + r.code, true); $('n').value = $('p').value = $('c').value = ''; load(); } catch (e) { say(e.message); } };
  $('assign').onclick = async () => { try { await post('/admin/affiliates/assign', { phone: $('ap').value, code: $('ac').value }); say('Customer assigned.', true); $('ap').value = $('ac').value = ''; load(); } catch (e) { say(e.message); } };
  load();
</script></body></html>'''
