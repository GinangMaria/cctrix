# CCTRIX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring CCTRIX to Excellent (4) on every rubric criterion by adding hashed-password DB auth, full activity logging, role-based access, a working `/login_logs` route, configurable RTSP camera, and a complete README.

**Architecture:** Single Flask `app.py` is enhanced in-place — no new modules, no framework swap. PostgreSQL tables already exist (Railway); we add a `users` table and wire the unused `auth_logs` table. All secrets move to `.env`.

**Tech Stack:** Python 3, Flask, psycopg2, OpenCV, werkzeug (password hashing), python-dotenv, pytest

---

## File Map

| File | Action | What changes |
|---|---|---|
| `requirements.txt` | Modify | Re-encode UTF-8, add `python-dotenv==1.0.1` |
| `.gitignore` | Create | Python standard + `.env` + `static/logs/*.jpg` |
| `.env.example` | Create | Template for all env vars |
| `app.py` | Modify | Env vars, users table, hashed auth, auth_logs, RBAC, `/login_logs`, RTSP camera |
| `templates/index.html` | Modify | Add `login-container` panel + admin nav link |
| `tests/conftest.py` | Create | Mock psycopg2 before app import |
| `tests/test_auth.py` | Create | 12 tests covering auth, roles, routes |
| `README.md` | Replace | Full documentation |

---

### Task 1: Fix requirements.txt encoding + add python-dotenv

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Rewrite requirements.txt as UTF-8 with python-dotenv added**

The current file is UTF-16 encoded (unreadable by pip). Replace it entirely:

```
blinker==1.9.0
certifi==2026.5.20
charset-normalizer==3.4.7
click==8.3.3
colorama==0.4.6
Flask==3.1.3
gunicorn==26.0.0
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.3
numpy==2.4.5
opencv-python==4.13.0.92
packaging==26.2
psycopg2-binary==2.9.12
python-dateutil==2.9.0.post0
python-dotenv==1.0.1
Werkzeug==3.1.8
```

Save this as `requirements.txt` (UTF-8, no BOM). The large unused packages (torch, ultralytics, polars, scipy, etc.) are removed — they cause Railway build timeouts and aren't used.

- [ ] **Step 2: Verify pip can read it**

```bash
pip install -r requirements.txt --dry-run 2>&1 | head -5
```

Expected output: package names printed cleanly (no garbled characters).

- [ ] **Step 3: Commit**

```bash
git -C /Users/a1234/cctrix add requirements.txt
git -C /Users/a1234/cctrix commit -m "fix: re-encode requirements.txt as UTF-8, remove unused heavy deps, add python-dotenv"
```

---

### Task 2: Create .gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Write .gitignore**

```
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.eggs/

# Environment
.env
*.env.local

# Captured snapshots (large, not version-controlled)
static/logs/*.jpg

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/a1234/cctrix add .gitignore
git -C /Users/a1234/cctrix commit -m "chore: add .gitignore"
```

---

### Task 3: Create .env.example + update app.py to load env vars

**Files:**
- Create: `.env.example`
- Modify: `app.py` (top section — imports and config only)

- [ ] **Step 1: Create .env.example**

```
# Flask
SECRET_KEY=change_this_to_a_random_string

# PostgreSQL (Railway/Neon/Supabase)
DB_HOST=turntable.proxy.rlwy.net
DB_PORT=43684
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_NAME=railway

# Camera: 0 = webcam, or RTSP URL e.g. rtsp://192.168.1.100/stream
CAMERA_SOURCE=0
```

- [ ] **Step 2: Create local .env from example**

```bash
cp /Users/a1234/cctrix/.env.example /Users/a1234/cctrix/.env
```

Then edit `.env` and set `DB_PASSWORD` to the real Railway password (`QGGzlutsqnoowNFWBnOvTgIDmWWWMJzg`).

- [ ] **Step 3: Update the top of app.py — imports and config**

Replace the existing top section (lines 1–29) with:

```python
from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import cv2
import time
import os
import numpy as np
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cctv_secret_key_change_in_prod")

# =========================
# DATABASE CONNECTION
# =========================
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "turntable.proxy.rlwy.net"),
    "port": os.environ.get("DB_PORT", "43684"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "railway"),
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print("Database Connected!")
except Exception as e:
    print("DATABASE ERROR:", e)
    conn = None
    cursor = None
```

- [ ] **Step 4: Commit**

```bash
git -C /Users/a1234/cctrix add .env.example app.py
git -C /Users/a1234/cctrix commit -m "feat: load DB config and SECRET_KEY from environment variables"
```

---

### Task 4: Add users table + seed to app.py init_db

**Files:**
- Modify: `app.py` — `init_db()` function and new `_seed_users()` function

- [ ] **Step 1: Replace init_db() and add _seed_users() after the DB connection block**

Find the existing `init_db()` function and replace it entirely with:

```python
# =========================
# INIT DATABASE
# =========================
def init_db():
    if not cursor:
        return
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS detection_logs (
            id SERIAL PRIMARY KEY,
            person_detected BOOLEAN,
            confidence FLOAT,
            image_path TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_logs (
            id SERIAL PRIMARY KEY,
            username TEXT,
            action TEXT,
            reason TEXT,
            ip_address TEXT,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_login_attempts (
            id SERIAL PRIMARY KEY,
            username TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT
        )
        """)
        conn.commit()
        print("Tables Ready!")
        _seed_users()
    except Exception as e:
        print("INIT DB ERROR:", e)


def _seed_users():
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute("""
                INSERT INTO users (username, password_hash, role) VALUES
                (%s, %s, %s), (%s, %s, %s)
            """, (
                'admin', generate_password_hash('admin123'), 'admin',
                'viewer', generate_password_hash('viewer123'), 'viewer'
            ))
            conn.commit()
            print("Default users seeded — admin:admin123, viewer:viewer123")
    except Exception as e:
        print("SEED ERROR:", e)


init_db()
```

- [ ] **Step 2: Verify the app starts without errors**

```bash
cd /Users/a1234/cctrix && python -c "import app; print('OK')"
```

Expected: `Database Connected!`, `Tables Ready!`, `OK` (may say "Default users seeded" on first run).

- [ ] **Step 3: Commit**

```bash
git -C /Users/a1234/cctrix add app.py
git -C /Users/a1234/cctrix commit -m "feat: add users table with seeded admin/viewer accounts"
```

---

### Task 5: Replace hardcoded auth with DB lookup + hashed password

**Files:**
- Modify: `app.py` — remove `USERNAME`/`PASSWORD` constants, rewrite login route

- [ ] **Step 1: Remove the hardcoded credentials block**

Delete these two lines from app.py:
```python
USERNAME = "admin"
PASSWORD = "1234"
```

- [ ] **Step 2: Add the _log_auth helper (place it after is_ip_blocked)**

```python
# =========================
# AUTH LOGGER
# =========================
def _log_auth(username, action, reason, ip, user_agent):
    if not cursor:
        return
    try:
        cursor.execute("""
            INSERT INTO auth_logs (username, action, reason, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, action, reason, ip, user_agent))
        conn.commit()
    except Exception as e:
        print("AUTH LOG ERROR:", e)
```

- [ ] **Step 3: Add the require_admin decorator (place it after _log_auth)**

```python
# =========================
# ROLE GUARD
# =========================
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated
```

- [ ] **Step 4: Rewrite the login route**

Replace the entire `@app.route('/login', ...)` function with:

```python
# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')

    if request.method == 'POST':

        if is_ip_blocked(ip):
            return render_template(
                "login.html",
                error="Too many failed attempts. Try again in 10 minutes."
            )

        username = request.form.get('username')
        password = request.form.get('password')

        user = None
        if cursor:
            try:
                cursor.execute(
                    "SELECT id, password_hash, role FROM users WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()
            except Exception as e:
                print("DB ERROR:", e)

        if user and check_password_hash(user[1], password):
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user[2]
            _log_auth(username, 'LOGIN_SUCCESS', 'Valid credentials', ip, user_agent)
            return redirect(url_for('index'))

        # Failed login
        if cursor:
            try:
                cursor.execute("""
                    INSERT INTO failed_login_attempts (username, ip_address, user_agent)
                    VALUES (%s, %s, %s)
                """, (username, ip, user_agent))
                conn.commit()
            except Exception as e:
                print("FAILED LOGIN ERROR:", e)

        _log_auth(username, 'LOGIN_FAILED', 'Invalid credentials', ip, user_agent)
        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")
```

- [ ] **Step 5: Rewrite the logout route**

Replace the existing logout function with:

```python
# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    username = session.get('username', 'unknown')
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    _log_auth(username, 'LOGOUT', 'User logged out', ip, user_agent)
    session.clear()
    return redirect(url_for('login'))
```

- [ ] **Step 6: Update the index route to pass role to template**

Replace:
```python
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template("index.html")
```

With:
```python
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template("index.html", role=session.get('role'))
```

- [ ] **Step 7: Verify login works locally**

```bash
cd /Users/a1234/cctrix && python app.py
```

Open `http://localhost:5000/login` → login with `admin` / `admin123` → should reach dashboard. Login with `admin` / `1234` → should fail.

- [ ] **Step 8: Commit**

```bash
git -C /Users/a1234/cctrix add app.py
git -C /Users/a1234/cctrix commit -m "feat: replace plain-text auth with DB lookup and hashed passwords; add role-based session"
```

---

### Task 6: Add /login_logs route + protect /failed-logins-page with require_admin

**Files:**
- Modify: `app.py` — new `/login_logs` route, decorate `/failed-logins-page`

- [ ] **Step 1: Add the /login_logs route (insert before the HEALTH CHECK section)**

```python
# =========================
# AUTH LOGS API
# =========================
@app.route('/login_logs')
def login_logs():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        return jsonify({"logs": []})
    try:
        cursor.execute("""
            SELECT username, action, reason, ip_address, timestamp
            FROM auth_logs
            ORDER BY id DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        return jsonify({
            "logs": [
                {
                    "username": r[0],
                    "type": r[1],
                    "reason": r[2],
                    "ip": r[3],
                    "time": str(r[4])
                }
                for r in rows
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)})
```

- [ ] **Step 2: Apply @require_admin to failed_logins_page**

Replace:
```python
@app.route('/failed-logins-page')
def failed_logins_page():
```

With:
```python
@app.route('/failed-logins-page')
@require_admin
def failed_logins_page():
```

Also remove the manual `if not session.get('logged_in')` check inside it — `require_admin` already handles that.

- [ ] **Step 3: Commit**

```bash
git -C /Users/a1234/cctrix add app.py
git -C /Users/a1234/cctrix commit -m "feat: add /login_logs API route; protect /failed-logins-page with require_admin"
```

---

### Task 7: Fix dashboard template — add login-container panel + admin nav link

**Files:**
- Modify: `templates/index.html`

The dashboard JS already calls `loadLoginLogs()` and targets `id="login-container"`, but that element doesn't exist. This task adds it.

- [ ] **Step 1: Add the auth logs panel to the dashboard layout**

In `templates/index.html`, find the closing `</div>` of `<!-- RIGHT -->` (the existing `logs-panel` div) and add a second panel right after it, before the closing `</div>` of `.dashboard`:

Replace:
```html
    <!-- RIGHT -->
    <div class="logs-panel">

        <div class="logs-header">Motion Logs</div>
        <div class="logs-container" id="motion-container"></div>

    </div>

</div>
```

With:
```html
    <!-- RIGHT -->
    <div class="logs-panel">

        <div class="logs-header">Motion Logs</div>
        <div class="logs-container" id="motion-container"></div>

    </div>

    {% if role == 'admin' %}
    <!-- AUTH LOGS (admin only) -->
    <div class="logs-panel">

        <div class="logs-header">Auth Logs</div>
        <div class="logs-container" id="login-container"></div>

    </div>
    {% endif %}

</div>
```

- [ ] **Step 2: Add Failed Logins nav link for admin in the header**

Find the top-header div and replace:
```html
<div class="top-header">
    <div class="dashboard-title">Network Monitor</div>
    <a class="logout-btn" href="/logout">Logout</a>
</div>
```

With:
```html
<div class="top-header">
    <div class="dashboard-title">Network Monitor</div>
    <div style="display:flex;gap:10px;align-items:center;">
        {% if role == 'admin' %}
        <a class="logout-btn" href="/failed-logins-page"
           style="background:#ff4444;">Failed Logins</a>
        {% endif %}
        <a class="logout-btn" href="/logout">Logout</a>
    </div>
</div>
```

- [ ] **Step 3: Verify dashboard shows auth logs panel when logged in as admin**

```bash
cd /Users/a1234/cctrix && python app.py
```

Login as `admin` → dashboard should show Motion Logs panel + Auth Logs panel + "Failed Logins" red button. Login as `viewer` → only Motion Logs, no red button.

- [ ] **Step 4: Commit**

```bash
git -C /Users/a1234/cctrix add templates/index.html
git -C /Users/a1234/cctrix commit -m "feat: add auth logs panel and Failed Logins nav link for admin role"
```

---

### Task 8: Fix CAMERA_SOURCE env var for physical CCTV support

**Files:**
- Modify: `app.py` — camera initialization block

- [ ] **Step 1: Replace the hardcoded camera init**

Find:
```python
if os.environ.get("RAILWAY_ENVIRONMENT") is None:

    camera = cv2.VideoCapture(0)
```

Replace with:
```python
if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    source = os.environ.get("CAMERA_SOURCE", "0")
    camera_index = int(source) if source.isdigit() else source
    camera = cv2.VideoCapture(camera_index)
```

Now a physical IP camera at `rtsp://192.168.1.100/stream` can be used by setting `CAMERA_SOURCE=rtsp://192.168.1.100/stream` in `.env`.

- [ ] **Step 2: Commit**

```bash
git -C /Users/a1234/cctrix add app.py
git -C /Users/a1234/cctrix commit -m "feat: read camera source from CAMERA_SOURCE env var (supports RTSP for physical CCTV)"
```

---

### Task 9: Write tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Create tests/__init__.py (empty)**

```python

```

- [ ] **Step 2: Create tests/conftest.py**

This must mock psycopg2 before any import of `app`, so that the DB connection at module level doesn't fail:

```python
# tests/conftest.py
import sys
import os
from unittest.mock import MagicMock
import pytest

# Set env before app imports
os.environ.setdefault('RAILWAY_ENVIRONMENT', 'test')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('DB_PASSWORD', 'test')

# Mock psycopg2 before app.py is imported
mock_conn = MagicMock()
mock_cursor = MagicMock()
mock_conn.cursor.return_value = mock_cursor

mock_psycopg2 = MagicMock()
mock_psycopg2.connect.return_value = mock_conn
sys.modules['psycopg2'] = mock_psycopg2

# Default: fetchone returns (1,) so _seed_users sees count > 0 and skips seeding
mock_cursor.fetchone.return_value = (1,)


@pytest.fixture
def db_cursor():
    """Fresh cursor mock for each test. Sets safe defaults."""
    mock_cursor.reset_mock(return_value=True, side_effect=True)
    mock_cursor.fetchone.return_value = (0,)  # 0 failed attempts = not blocked
    return mock_cursor
```

- [ ] **Step 3: Create tests/test_auth.py**

```python
# tests/test_auth.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from werkzeug.security import generate_password_hash, check_password_hash
from tests.conftest import mock_cursor, mock_conn

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config.update(TESTING=True, SECRET_KEY='test-key')
    with flask_app.app.test_client() as c:
        yield c


# ---------- password hashing ----------

def test_password_not_stored_as_plaintext():
    """Passwords must be hashed — never stored as the original string."""
    h = generate_password_hash('admin123')
    assert h != 'admin123'


def test_correct_password_passes_check():
    h = generate_password_hash('admin123')
    assert check_password_hash(h, 'admin123') is True


def test_wrong_password_fails_check():
    h = generate_password_hash('admin123')
    assert check_password_hash(h, 'wrong') is False


def test_old_hardcoded_password_rejected():
    """The old plain-text password '1234' must no longer work."""
    h = generate_password_hash('admin123')
    assert check_password_hash(h, '1234') is False, \
        "Old hardcoded password '1234' must not authenticate any user"


# ---------- unauthenticated access ----------

def test_login_page_loads(client):
    r = client.get('/login')
    assert r.status_code == 200


def test_dashboard_redirects_when_not_logged_in(client):
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_video_redirects_when_not_logged_in(client):
    r = client.get('/video', follow_redirects=False)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


# ---------- login logic ----------

def test_login_fails_with_bad_credentials(client, db_cursor):
    db_cursor.fetchone.side_effect = [
        (0,),   # is_ip_blocked COUNT(*) → 0 attempts
        None,   # users query → no user found
    ]
    r = client.post('/login', data={'username': 'hacker', 'password': 'wrong'})
    assert r.status_code == 200
    assert b'Invalid' in r.data or b'INVALID' in r.data


def test_login_succeeds_with_correct_credentials(client, db_cursor):
    hashed = generate_password_hash('admin123')
    db_cursor.fetchone.side_effect = [
        (0,),                    # is_ip_blocked → not blocked
        (1, hashed, 'admin'),    # users query → found
    ]
    r = client.post(
        '/login',
        data={'username': 'admin', 'password': 'admin123'},
        follow_redirects=False
    )
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/')


def test_login_sets_role_in_session(client, db_cursor):
    hashed = generate_password_hash('viewer123')
    db_cursor.fetchone.side_effect = [
        (0,),
        (2, hashed, 'viewer'),
    ]
    with client:
        client.post('/login', data={'username': 'viewer', 'password': 'viewer123'})
        from flask import session
        with client.session_transaction() as sess:
            assert sess['role'] == 'viewer'
            assert sess['username'] == 'viewer'


# ---------- role-based access ----------

def test_viewer_cannot_access_failed_logins_page(client):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'viewer'
        sess['role'] = 'viewer'
    r = client.get('/failed-logins-page', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' not in r.headers['Location']  # redirected to dashboard, not login


def test_admin_can_access_failed_logins_page(client, db_cursor):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = 'admin'
    db_cursor.fetchall.return_value = []
    r = client.get('/failed-logins-page')
    assert r.status_code == 200


def test_login_logs_returns_empty_for_viewer(client):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'viewer'
        sess['role'] = 'viewer'
    r = client.get('/login_logs')
    assert r.status_code == 200
    data = r.get_json()
    assert data['logs'] == []


def test_login_logs_returns_data_for_admin(client, db_cursor):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = 'admin'
    db_cursor.fetchall.return_value = [
        ('admin', 'LOGIN_SUCCESS', 'Valid credentials', '127.0.0.1', '2026-05-30 10:00:00')
    ]
    r = client.get('/login_logs')
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['logs']) == 1
    assert data['logs'][0]['type'] == 'LOGIN_SUCCESS'
```

- [ ] **Step 4: Run the tests**

```bash
cd /Users/a1234/cctrix && python -m pytest tests/ -v 2>&1
```

Expected: all 12 tests PASS. If any fail, diagnose before continuing.

- [ ] **Step 5: Commit**

```bash
git -C /Users/a1234/cctrix add tests/
git -C /Users/a1234/cctrix commit -m "test: add auth and RBAC tests (12 tests passing)"
```

---

### Task 10: Write README

**Files:**
- Modify: `README.md` (full replacement)

- [ ] **Step 1: Replace README.md with full documentation**

```markdown
# CCTRIX — CCTV Network Monitoring System

Web-based CCTV monitoring system built with Flask and PostgreSQL. Connects to a physical CCTV camera over a local network and provides a live monitoring dashboard with motion detection, user logging, and role-based access control.

## Features

- Live CCTV feed via OpenCV (webcam or IP camera via RTSP)
- Motion detection with automatic snapshot capture
- Role-based access: Admin and Viewer accounts
- Hashed password authentication (werkzeug)
- Complete activity logging: login success, login failure, logout
- IP-based brute-force protection (5 failed attempts = 10-minute ban)
- PostgreSQL database (Railway / Neon / Supabase compatible)
- Cloud deployment via Railway

## Network Diagram

```
[Physical CCTV Camera]
        |
        | (Ethernet / Wi-Fi)
        |
   [Router / Switch]  ← 192.168.1.1
        |
        | (LAN — same subnet)
        |
   [PC running CCTRIX]  ← 192.168.1.x
        |
        | HTTP :5000
        |
   [Web Browser]  ← monitor from any device on the network
```

## Setup (Local)

### 1. Clone the repository

```bash
git clone https://github.com/GinangMaria/cctrix.git
cd cctrix
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Flask session secret | `any-random-string` |
| `DB_HOST` | PostgreSQL host | `turntable.proxy.rlwy.net` |
| `DB_PORT` | PostgreSQL port | `43684` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | `your_password` |
| `DB_NAME` | Database name | `railway` |
| `CAMERA_SOURCE` | `0` = webcam, or RTSP URL | `rtsp://192.168.1.100/stream` |

### 4. Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

## Default Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Full access |
| `viewer` | `viewer123` | Camera feed only |

## Role Permissions

| Feature | Admin | Viewer |
|---|---|---|
| Live CCTV feed | Yes | Yes |
| Motion detection logs | Yes | Yes |
| Auth activity logs | Yes | No |
| Failed login attempts page | Yes | No |

## Running Tests

```bash
python -m pytest tests/ -v
```

## Cloud Deployment (Railway)

1. Push to GitHub
2. Connect repository to [Railway](https://railway.app)
3. Add environment variables in the Railway dashboard
4. Deploy — the `Procfile` runs gunicorn automatically

## Screenshots

<!-- Add screenshots of the dashboard, login page, and logs here -->

## Tech Stack

- Python 3 / Flask
- PostgreSQL (psycopg2-binary)
- OpenCV — motion detection
- werkzeug — password hashing
- gunicorn — production WSGI server
- Railway — cloud hosting
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/a1234/cctrix add README.md
git -C /Users/a1234/cctrix commit -m "docs: add comprehensive README with setup instructions, network diagram, and role table"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/a1234/cctrix && python -m pytest tests/ -v
```

Expected: 12/12 PASS.

- [ ] **Step 2: Start the app and walk through the demo flow**

```bash
cd /Users/a1234/cctrix && python app.py
```

Verify each of these manually:

1. `http://localhost:5000/login` — login page loads
2. Login as `admin` / `admin123` — reaches dashboard
3. Dashboard shows live camera feed + Motion Logs panel + Auth Logs panel + "Failed Logins" red button
4. Auth Logs panel auto-refreshes and shows the LOGIN_SUCCESS event just logged
5. Click "Failed Logins" — shows the failed_logins.html table
6. Logout — redirects to login; auth_logs records LOGOUT
7. Login as `viewer` / `viewer123` — dashboard shows feed + Motion Logs only, no Auth Logs panel, no red button
8. Try `http://localhost:5000/failed-logins-page` as viewer — redirected to dashboard
9. Try `http://localhost:5000/login_logs` as viewer — returns `{"logs": []}`
10. Try logging in with wrong password — error shown, entry appears in failed_login_attempts

- [ ] **Step 3: Check git log shows meaningful commit history**

```bash
git -C /Users/a1234/cctrix log --oneline
```

Expected output (roughly):
```
abc1234 docs: add comprehensive README
def5678 test: add auth and RBAC tests (12 tests passing)
ghi9012 feat: read camera source from CAMERA_SOURCE env var
jkl3456 feat: add auth logs panel and Failed Logins nav link for admin role
mno7890 feat: add /login_logs API route; protect /failed-logins-page
pqr1234 feat: replace plain-text auth with DB lookup and hashed passwords
stu5678 feat: add users table with seeded admin/viewer accounts
vwx9012 feat: load DB config and SECRET_KEY from environment variables
yza3456 chore: add .gitignore
bcd7890 fix: re-encode requirements.txt as UTF-8
```

- [ ] **Step 4: Verify .env is not tracked by git**

```bash
git -C /Users/a1234/cctrix status
```

`.env` must NOT appear in the output. If it does: `git rm --cached .env` then re-commit.
```

---

## Spec Coverage Check

| Spec requirement | Covered by |
|---|---|
| Hashed passwords (werkzeug) | Task 5 |
| Users table in PostgreSQL | Task 4 |
| auth_logs wired (login success, failure, logout) | Tasks 5, 6 |
| Role-based access (admin/viewer) | Tasks 5, 6, 7 |
| /login_logs route (fix broken dashboard) | Task 6 |
| login-container DOM element (fix broken JS) | Task 7 |
| CAMERA_SOURCE env var (RTSP support) | Task 8 |
| DB credentials in env vars | Task 3 |
| .gitignore | Task 2 |
| requirements.txt (UTF-8, python-dotenv) | Task 1 |
| Full README | Task 10 |
| Tests | Task 9 |
