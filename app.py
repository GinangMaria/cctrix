from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import cv2
import time
import os
import json
import urllib.request
import urllib.parse
import numpy as np
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cctv_secret_key_change_in_prod")

# reCAPTCHA v2 — uses Google's official test keys by default (always pass).
# Replace with real keys from https://www.google.com/recaptcha/admin in production.
RECAPTCHA_SITE_KEY   = os.environ.get("RECAPTCHA_SITE_KEY",   "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MFLZsRwt")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ17ZFtSe")

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

# =========================
# FOLDERS
# =========================
os.makedirs("static/logs", exist_ok=True)

# =========================
# CAMERA
# =========================

camera = None

# Railway has NO webcam
# Webcam only works locally
# Set CAMERA_SOURCE=0 for webcam, or RTSP URL for IP camera

if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    source = os.environ.get("CAMERA_SOURCE", "0")
    camera_index = int(source) if source.isdigit() else source
    camera = cv2.VideoCapture(camera_index)

previous_frame = None
motion_active = False
last_capture_time = 0
last_motion_time = 0
stable_motion_state = False

# =========================
# LOGIN CHECK
# =========================
def is_ip_blocked(ip):

    try:

        time_limit = datetime.now() - timedelta(minutes=10)

        cursor.execute("""
            SELECT COUNT(*)
            FROM failed_login_attempts
            WHERE ip_address = %s
            AND attempted_at >= %s
        """, (ip, time_limit))

        count = cursor.fetchone()[0]

        return count >= 5

    except:
        return False

# =========================
# RECAPTCHA VERIFIER
# =========================
def _verify_recaptcha(token, ip):
    if not token:
        return False
    try:
        data = urllib.parse.urlencode({
            "secret": RECAPTCHA_SECRET_KEY,
            "response": token,
            "remoteip": ip,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://www.google.com/recaptcha/api/siteverify",
            data=data, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("success", False)
    except Exception as e:
        print("reCAPTCHA error:", e)
        return True  # fail open if Google is unreachable (dev safety)

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

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')

    def _render_login(error=None):
        return render_template("login.html", error=error, site_key=RECAPTCHA_SITE_KEY)

    if request.method == 'POST':

        if is_ip_blocked(ip):
            return _render_login("Too many failed attempts. Try again in 10 minutes.")

        # reCAPTCHA check
        recaptcha_token = request.form.get('g-recaptcha-response', '')
        if not _verify_recaptcha(recaptcha_token, ip):
            return _render_login("Please complete the reCAPTCHA verification.")

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
        return _render_login("Invalid username or password.")

    return _render_login()

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

# =========================
# DASHBOARD
# =========================
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template("index.html", role=session.get('role'))

# =========================
# VIDEO STREAM
# =========================
def generate_frames():

    global previous_frame
    global motion_active
    global last_capture_time
    global last_motion_time
    global stable_motion_state

    # Railway mode
    if camera is None:

        while True:

            blank = np.ones((500, 800, 3), dtype=np.uint8) * 255

            cv2.putText(
                blank,
                "Railway Cloud Mode - No Camera",
                (120, 250),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2
            )

            ret, buffer = cv2.imencode('.jpg', blank)

            frame_bytes = buffer.tobytes()

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame_bytes +
                b'\r\n'
            )

            time.sleep(0.1)

    while True:

        success, frame = camera.read()

        if not success:
            continue

        frame = cv2.flip(frame, 1)

        frame = cv2.resize(frame, (800, 500))

        display = frame.copy()

        clean = frame.copy()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if previous_frame is None:

            previous_frame = gray

            continue

        diff = cv2.absdiff(previous_frame, gray)

        thresh = cv2.threshold(
            diff,
            25,
            255,
            cv2.THRESH_BINARY
        )[1]

        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(
            thresh,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        motion = False

        for c in contours:

            if cv2.contourArea(c) < 1000:
                continue

            motion = True

            x, y, w, h = cv2.boundingRect(c)

            cv2.rectangle(
                display,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

        previous_frame = gray

        now = time.time()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if motion:

            last_motion_time = now

            stable_motion_state = True

            if not motion_active and now - last_capture_time > 5:

                motion_active = True

                last_capture_time = now

                filename = f"{int(now)}.jpg"

                path = os.path.join(
                    "static/logs",
                    filename
                )

                cv2.imwrite(path, clean)

                image_path = f"/static/logs/{filename}"

                try:

                    cursor.execute("""
                        INSERT INTO detection_logs (
                            person_detected,
                            confidence,
                            image_path
                        )
                        VALUES (%s, %s, %s)
                    """, (True, 0.90, image_path))

                    conn.commit()

                except Exception as e:
                    print("INSERT ERROR:", e)

        if now - last_motion_time > 2:
            stable_motion_state = False
        else:
            motion_active = False

        status = (
            "MOTION DETECTED"
            if stable_motion_state
            else "NO MOTION DETECTED"
        )

        cv2.putText(
            display,
            status,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255)
            if stable_motion_state
            else (255, 255, 255),
            2
        )

        cv2.putText(
            display,
            timestamp,
            (20, 480),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        ret, buffer = cv2.imencode('.jpg', display)

        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + frame_bytes +
            b'\r\n'
        )

# =========================
# VIDEO ROUTE
# =========================
@app.route('/video')
def video():

    if not session.get('logged_in'):

        return redirect(url_for('login'))

    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# =========================
# LOGS API
# =========================
@app.route('/logs')
def logs():

    try:

        cursor.execute("""
            SELECT
                person_detected,
                confidence,
                image_path,
                detected_at
            FROM detection_logs
            ORDER BY id DESC
            LIMIT 20
        """)

        rows = cursor.fetchall()

        return jsonify({
            "logs": [
                {
                    "person_detected": r[0],
                    "confidence": float(r[1]),
                    "image": r[2],
                    "time": str(r[3])
                }
                for r in rows
            ]
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# =========================
# FAILED LOGIN PAGE
# =========================
@app.route('/failed-logins-page')
@require_admin
def failed_logins_page():

    try:

        cursor.execute("""
            SELECT
                username,
                attempted_at,
                ip_address,
                user_agent
            FROM failed_login_attempts
            ORDER BY id DESC
            LIMIT 50
        """)

        rows = cursor.fetchall()

    except:
        rows = []

    return render_template(
        "failed_logins.html",
        logs=rows
    )

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

# =========================
# STATS API
# =========================
@app.route('/stats')
def stats():
    if not session.get('logged_in'):
        return jsonify({"error": "unauthorized"})
    try:
        from datetime import date
        today = date.today()
        cursor.execute("SELECT COUNT(*) FROM detection_logs WHERE detected_at::date = %s", (today,))
        motion_today = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM failed_login_attempts WHERE attempted_at::date = %s", (today,))
        failed_today = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM auth_logs WHERE timestamp::date = %s", (today,))
        auth_today = cursor.fetchone()[0]
        return jsonify({"motion_today": motion_today, "failed_logins_today": failed_today, "auth_events_today": auth_today})
    except Exception as e:
        return jsonify({"error": str(e), "motion_today": 0, "failed_logins_today": 0, "auth_events_today": 0})

# =========================
# EXPORT LOGS AS CSV (admin)
# =========================
@app.route('/export/motion')
@require_admin
def export_motion():
    from io import StringIO
    import csv as csv_mod
    output = StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(['ID', 'Person Detected', 'Confidence', 'Image Path', 'Detected At'])
    try:
        cursor.execute("SELECT id, person_detected, confidence, image_path, detected_at FROM detection_logs ORDER BY id DESC")
        for row in cursor.fetchall():
            writer.writerow(row)
    except Exception as e:
        writer.writerow(['Error', str(e)])
    from flask import make_response
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = 'attachment; filename=motion_logs.csv'
    return resp

@app.route('/export/auth')
@require_admin
def export_auth():
    from io import StringIO
    import csv as csv_mod
    output = StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(['ID', 'Username', 'Action', 'Reason', 'IP Address', 'User Agent', 'Timestamp'])
    try:
        cursor.execute("SELECT id, username, action, reason, ip_address, user_agent, timestamp FROM auth_logs ORDER BY id DESC")
        for row in cursor.fetchall():
            writer.writerow(row)
    except Exception as e:
        writer.writerow(['Error', str(e)])
    from flask import make_response
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = 'attachment; filename=auth_logs.csv'
    return resp

# =========================
# SYSTEM STATUS (admin)
# =========================
@app.route('/system-status')
@require_admin
def system_status():
    db_ok = False
    try:
        cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass
    cam_ok = camera is not None
    try:
        cursor.execute("SELECT COUNT(*) FROM detection_logs")
        total_motion = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM auth_logs")
        total_auth = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM failed_login_attempts")
        total_failed = cursor.fetchone()[0]
    except Exception:
        total_motion = total_auth = total_users = total_failed = 0
    return render_template('system_status.html',
        db_ok=db_ok, cam_ok=cam_ok,
        total_motion=total_motion, total_auth=total_auth,
        total_users=total_users, total_failed=total_failed,
        role=session.get('role'))

# =========================
# HEALTH CHECK
# =========================
@app.route('/health')
def health():
    return jsonify({"status": "ok"})

# =========================
# RUN APP
# =========================
if __name__ == '__main__':

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host='0.0.0.0',
        port=port
    )