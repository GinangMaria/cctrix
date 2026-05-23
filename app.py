from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
import cv2
import time
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cctv_secret_key"

# =========================
# LOGIN INFO
# =========================
USERNAME = "admin"
PASSWORD = "1234"

# =========================
# CAMERA SETUP
# =========================
camera = cv2.VideoCapture(0)

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
camera.set(cv2.CAP_PROP_FPS, 30)

# =========================
# LOG STORAGE
# =========================
motion_logs = []
login_logs_memory = []

previous_frame = None
motion_active = False
last_capture_time = 0

last_motion_time = 0
stable_motion_state = False


# =========================
# LOGIN ROUTE
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')

        if username == USERNAME and password == PASSWORD:

            session['logged_in'] = True

            login_logs_memory.insert(0, {
                "type": "SUCCESS",
                "username": username,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            login_logs_memory[:] = login_logs_memory[:20]

            return redirect(url_for('index'))

        else:

            login_logs_memory.insert(0, {
                "type": "FAILED",
                "username": username,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            login_logs_memory[:] = login_logs_memory[:20]

            return render_template('login.html', error=True)

    return render_template('login.html')


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

    return render_template('index.html')


# =========================
# CAMERA + MOTION DETECTION
# =========================
def generate_frames():

    global previous_frame, motion_logs, motion_active, last_capture_time
    global last_motion_time, stable_motion_state, camera

    while True:

        success, frame = camera.read()

        if not success:
            camera.release()
            time.sleep(1)
            camera = cv2.VideoCapture(0)
            continue

        frame = cv2.flip(frame, 1)
        frame = cv2.resize(frame, (800, 500))

        display_frame = frame.copy()
        clean_frame = frame.copy()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if previous_frame is None:
            previous_frame = gray
            continue

        frame_diff = cv2.absdiff(previous_frame, gray)

        thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_detected = False

        for contour in contours:
            if cv2.contourArea(contour) < 1000:
                continue

            motion_detected = True

            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        previous_frame = gray

        now = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # =========================
        # STABLE MOTION STATE
        # =========================
        if motion_detected:
            last_motion_time = now
            stable_motion_state = True

            if not motion_active and now - last_capture_time > 5:

                motion_active = True
                last_capture_time = now

                filename = f"{int(now)}.jpg"
                filepath = os.path.join("static", "logs", filename)

                cv2.imwrite(filepath, clean_frame)

                motion_logs.insert(0, {
                    "time": timestamp,
                    "image": f"/static/logs/{filename}"
                })

                motion_logs[:] = motion_logs[:20]

        if now - last_motion_time > 2:
            stable_motion_state = False
        else:
            motion_active = False

        # =========================
        # RIGHT SIDE CAMERA TEXT FIX
        # =========================

        status_text = "MOTION DETECTED" if stable_motion_state else "NO MOTION DETECTED"
        status_color = (0, 0, 255) if stable_motion_state else (255, 255, 255)

        (text_w, text_h), _ = cv2.getTextSize(
            status_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            2
        )

        x_position = 800 - text_w - 20  # RIGHT ALIGN

        cv2.putText(
            display_frame,
            status_text,
            (x_position, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            status_color,
            2
        )

        # timestamp (bottom-left)
        cv2.putText(
            display_frame,
            timestamp,
            (20, 480),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        # =========================
        # STREAM FRAME
        # =========================
        ret, buffer = cv2.imencode('.jpg', display_frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


# =========================
# VIDEO FEED
# =========================
@app.route('/video')
def video():

    if not session.get('logged_in'):
        return redirect(url_for('login'))

    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# =========================
# MOTION LOGS API
# =========================
@app.route('/logs')
def logs():

    if not session.get('logged_in'):
        return jsonify({"logs": []})

    return jsonify({"logs": motion_logs})


# =========================
# LOGIN LOGS API
# =========================
@app.route('/login_logs')
def login_logs():

    if not session.get('logged_in'):
        return jsonify({"logs": []})

    return jsonify({"logs": login_logs_memory})


# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
