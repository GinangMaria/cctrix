from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
import cv2
import time
import os
import numpy as np
from datetime import datetime, timedelta
import psycopg2

app = Flask(__name__)
app.secret_key = "cctv_secret_key"

# =========================
# DATABASE CONNECTION
# =========================
try:
    conn = psycopg2.connect(
        host="turntable.proxy.rlwy.net",
        port="43684",
        user="postgres",
        password="QGGzlutsqnoowNFWBnOvTgIDmWWWMJzg",
        database="railway"
    )

    cursor = conn.cursor()

    print("Database Connected!")

except Exception as e:
    print("Database Error:", e)

# =========================
# INIT DATABASE
# =========================
def init_db():

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
    CREATE TABLE IF NOT EXISTS failed_login_attempts (
        id SERIAL PRIMARY KEY,
        username TEXT,
        attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ip_address TEXT,
        user_agent TEXT
    )
    """)

    conn.commit()

init_db()

# =========================
# FOLDERS
# =========================
os.makedirs("static/logs", exist_ok=True)

# =========================
# LOGIN INFO
# =========================
USERNAME = "admin"
PASSWORD = "1234"

# =========================
# CAMERA
# =========================

camera = None

# Local camera only on your PC
if os.environ.get("RAILWAY_ENVIRONMENT") is None:

    try:
        camera = cv2.VideoCapture(0)

        if not camera.isOpened():
            camera = None

    except:
        camera = None

previous_frame = None
motion_active = False
last_capture_time = 0
last_motion_time = 0
stable_motion_state = False

# =========================
# LOGIN CHECK
# =========================
def is_ip_blocked(ip):

    time_limit = datetime.now() - timedelta(minutes=10)

    cursor.execute("""
        SELECT COUNT(*)
        FROM failed_login_attempts
        WHERE ip_address = %s
        AND attempted_at >= %s
    """, (ip, time_limit))

    count = cursor.fetchone()[0]

    return count >= 5

# =========================
# LOGIN ROUTE
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():

    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')

    if request.method == 'POST':

        if is_ip_blocked(ip):

            return render_template(
                "login.html",
                error="Too many failed attempts. Try again later."
            )

        username = request.form.get('username')
        password = request.form.get('password')

        if username == USERNAME and password == PASSWORD:

            session['logged_in'] = True

            return redirect(url_for('index'))

        # FAILED LOGIN
        cursor.execute("""
            INSERT INTO failed_login_attempts (
                username,
                ip_address,
                user_agent
            )
            VALUES (%s, %s, %s)
        """, (username, ip, user_agent))

        conn.commit()

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")

# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('login'))

# =========================
# DASHBOARD
# =========================
@app.route('/')
def index():

    if not session.get('logged_in'):

        return redirect(url_for('login'))

    return render_template("index.html")

# =========================
# CCTV STREAM
# =========================
def generate_frames():

    global previous_frame
    global motion_active
    global last_capture_time
    global last_motion_time
    global stable_motion_state

    # =========================
    # NO CAMERA AVAILABLE
    # =========================
    if camera is None:

        while True:

            blank = np.ones((500, 800, 3), dtype=np.uint8) * 255

            cv2.putText(
                blank,
                "NO CAMERA AVAILABLE ON RAILWAY",
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

    # =========================
    # CAMERA LOOP
    # =========================
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

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

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

                cursor.execute("""
                    INSERT INTO detection_logs (
                        person_detected,
                        confidence,
                        image_path
                    )
                    VALUES (%s, %s, %s)
                """, (True, 0.90, image_path))

                conn.commit()

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
# DETECTION LOGS API
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
# FAILED LOGINS PAGE
# =========================
@app.route('/failed-logins-page')
def failed_logins_page():

    if not session.get('logged_in'):

        return redirect(url_for('login'))

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

    return render_template(
        "failed_logins.html",
        logs=rows
    )

# =========================
# HEALTH CHECK
# =========================
@app.route('/health')
def health():

    return "CCTV System Running"

# =========================
# RUN APP
# =========================
if __name__ == '__main__':

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )