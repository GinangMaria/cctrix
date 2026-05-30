# CCTRIX Improvements Design

**Date:** 2026-05-30  
**Project:** CCTRIX — CCTV Network Monitoring System  
**Rubric:** COMP 012 Network Administration, PUP Santa Rosa

---

## Goal

Bring the existing Flask/PostgreSQL CCTV monitoring app to "Excellent (4)" on all rubric criteria, with a local-first demo focus. No framework swap, no rewrites — improvements layer onto `app.py`.

---

## Rubric Gap Analysis

| Criterion | Current | Target |
|---|---|---|
| Security | Password plain text, no logging of success/logout | Hashed passwords, full auth_logs |
| Auth Logs | Only failed logins stored; `/login_logs` route missing | All events logged; route added |
| Role-based access | Single hardcoded admin | admin + viewer roles from DB |
| PostgreSQL | `auth_logs` table defined but unused | All tables fully wired |
| README | One line (`# cctrix`) | Full setup doc with diagram |
| Camera | Webcam hardcoded to index 0 | Configurable via `CAMERA_SOURCE` env var |

---

## Database Schema

### New table: `users`
```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Seed on first run (if table is empty):
- `admin` / `admin123` / role=admin
- `viewer` / `viewer123` / role=viewer

Both passwords hashed with `werkzeug.security.generate_password_hash`.

### Existing table: `auth_logs` (wire it up)
Already defined in `database.py` but never inserted into from `app.py`.

```sql
-- already exists, just use it:
auth_logs(id, username, action, reason, ip_address, user_agent, timestamp)
```

Actions to log:
- `LOGIN_SUCCESS` — on correct credentials
- `LOGIN_FAILED` — on wrong credentials (in addition to existing `failed_login_attempts`)
- `LOGOUT` — on session clear

### Existing tables (no change)
- `detection_logs` — motion capture snapshots
- `failed_login_attempts` — IP blocking (already works)

---

## Authentication Flow

### Login (`POST /login`)
1. Check if IP is blocked (existing logic — keep it)
2. Query `users` table by username
3. If found: `check_password_hash(user.password_hash, submitted_password)`
4. On success: set `session['logged_in'] = True`, `session['username']`, `session['role']`; insert `auth_logs` LOGIN_SUCCESS
5. On failure: insert `auth_logs` LOGIN_FAILED + `failed_login_attempts`; return error

### Logout (`GET /logout`)
1. Get `session['username']` before clearing
2. Insert `auth_logs` LOGOUT
3. `session.clear()`
4. Redirect to login

---

## Role-Based Access

Two roles stored in `session['role']`:

| Route | admin | viewer |
|---|---|---|
| `/` (dashboard + camera) | ✅ | ✅ |
| `/video` (stream) | ✅ | ✅ |
| `/logs` (motion API) | ✅ | ✅ |
| `/login_logs` (auth log API) | ✅ | ❌ → 403 |
| `/failed-logins-page` | ✅ | ❌ → redirect dashboard |

Helper decorator `require_role('admin')` wraps restricted routes.

---

## New / Fixed Routes

### `GET /login_logs` (NEW)
Currently called by dashboard JS but returns 404. Fix:
```python
@app.route('/login_logs')
def login_logs():
    # requires logged_in
    # returns last 50 auth_logs as JSON
    # {logs: [{username, action, reason, ip_address, time}]}
```

### Dashboard JS
The JS already polls `/login_logs` every 2 seconds and renders results — it just needs the route to exist. No JS changes required.

---

## Environment Variables

Move hardcoded values to environment (loaded via `python-dotenv` for local, actual env vars on Railway):

| Var | Default | Description |
|---|---|---|
| `DB_HOST` | `turntable.proxy.rlwy.net` | PostgreSQL host |
| `DB_PORT` | `43684` | PostgreSQL port |
| `DB_USER` | `postgres` | DB user |
| `DB_PASSWORD` | *(required)* | DB password |
| `DB_NAME` | `railway` | DB name |
| `CAMERA_SOURCE` | `0` | `0`=webcam, or RTSP URL string |
| `SECRET_KEY` | *(required)* | Flask session secret |

A `.env.example` file is added; `.env` added to `.gitignore`.

---

## Camera Configuration

```python
source = os.environ.get("CAMERA_SOURCE", "0")
camera_index = int(source) if source.isdigit() else source
camera = cv2.VideoCapture(camera_index)
```

This lets a physical IP camera at `rtsp://192.168.1.x/stream` be used without code changes.

---

## GitHub / README

Replace `# cctrix` with a full README containing:
1. Project title + description
2. Features list
3. Network diagram (ASCII art: Camera → Router → PC running CCTRIX)
4. Setup instructions (clone, pip install, .env setup, run)
5. Environment variables table
6. Screenshots section (placeholder headings)
7. Default login credentials note

Add proper `.gitignore` (Python standard: `__pycache__`, `*.pyc`, `.env`, `static/logs/*.jpg`).

---

## What Is NOT Changed

- UI/UX styling (not scored by rubric)
- Motion detection algorithm
- Cloud deployment target (Railway stays)
- `requirements.txt` content (only fix encoding from UTF-16 to UTF-8)

---

## Files Modified

| File | Change |
|---|---|
| `app.py` | Auth from DB, hashed passwords, auth_logs wired, `/login_logs` route, role checks, env vars |
| `database.py` | Add `users` table init + seed function |
| `requirements.txt` | Re-save as UTF-8; add `python-dotenv` |
| `.env.example` | New file — template for env vars |
| `.gitignore` | New file — Python standard |
| `README.md` | Full replacement |
| `templates/login.html` | No change |
| `templates/index.html` | No change (JS already polls `/login_logs`) |
| `templates/failed_logins.html` | No change |
