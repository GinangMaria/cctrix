import psycopg2

DB_CONFIG = {
    "host": "turntable.proxy.rlwy.net",
    "port": "43684",
    "user": "postgres",
    "password": "YOUR_PASSWORD",
    "database": "railway"
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()


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
        ip_address TEXT,
        user_agent TEXT,
        attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()


def log(query, values):
    cursor.execute(query, values)
    conn.commit()