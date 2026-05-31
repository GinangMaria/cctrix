# tests/conftest.py
import sys
import os
from unittest.mock import MagicMock
import pytest

# Set env before app imports — these override any .env values in test mode
os.environ['RAILWAY_ENVIRONMENT'] = 'test'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DB_PASSWORD'] = 'test'
# Force the test reCAPTCHA bypass key so real .env key doesn't break login tests
os.environ['RECAPTCHA_SECRET_KEY'] = '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ17ZFtSe'

# Mock cv2 before app.py is imported (not available in test env)
sys.modules['cv2'] = MagicMock()

# Mock psycopg2 before app.py is imported
mock_conn = MagicMock()
mock_cursor = MagicMock()
mock_cursor.__bool__ = lambda self: True   # so `if cursor:` in app.py evaluates to True
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
