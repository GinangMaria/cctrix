# tests/test_auth.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from werkzeug.security import generate_password_hash, check_password_hash
from tests.conftest import mock_cursor, mock_conn

# Python 3.9 system hashlib on macOS lacks scrypt support; use pbkdf2 instead.
_HASH_METHOD = 'pbkdf2:sha256'


def _hash(password: str) -> str:
    return generate_password_hash(password, method=_HASH_METHOD)

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config.update(TESTING=True, SECRET_KEY='test-key')
    with flask_app.app.test_client() as c:
        yield c


# ---------- password hashing ----------

def test_password_not_stored_as_plaintext():
    """Passwords must be hashed — never stored as the original string."""
    h = _hash('admin123')
    assert h != 'admin123'


def test_correct_password_passes_check():
    h = _hash('admin123')
    assert check_password_hash(h, 'admin123') is True


def test_wrong_password_fails_check():
    h = _hash('admin123')
    assert check_password_hash(h, 'wrong') is False


def test_old_hardcoded_password_rejected():
    """The old plain-text password '1234' must no longer work."""
    h = _hash('admin123')
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
    hashed = _hash('admin123')
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
    hashed = _hash('viewer123')
    db_cursor.fetchone.side_effect = [
        (0,),
        (2, hashed, 'viewer'),
    ]
    client.post('/login', data={'username': 'viewer', 'password': 'viewer123'})
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
