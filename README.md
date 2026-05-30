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
