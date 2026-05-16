"""
conftest.py - Shared fixtures for unit and Selenium tests.
Uses a separate in-memory SQLite DB so the production database is never touched.
"""

import os
import time
import socket
import threading
import pytest

# Point to a fresh in-memory SQLite DB before importing the app
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("TMDB_API_KEY", "test_api_key")
os.environ.setdefault("TMDB_READ_TOKEN", "test_read_token")

from app import app as flask_app, db as _db


# ─────────────────────────────────────────────
# Unit-test fixtures  (in-memory DB, test client)
# ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Configure the Flask application for testing with an isolated in-memory database."""
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,       # disable CSRF so form POSTs work in unit tests
        SERVER_NAME="localhost",
    )

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """Provide a clean database session for every test function."""
    with app.app_context():
        yield _db
        _db.session.remove()
        # Truncate all tables between tests
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture(scope="function")
def client(app, db):
    """A Flask test client with a fresh database for every test."""
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="function")
def auth_client(client, db):
    """
    A test client that is already logged in as a standard test user.
    Returns (client, user) so tests can reference the user object.
    """
    from werkzeug.security import generate_password_hash
    from app import User

    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=generate_password_hash("password123"),
    )
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login",
        data={"email": "test@example.com", "password": "password123"},
        follow_redirects=True,
    )
    return client, user


# ─────────────────────────────────────────────
# Live-server fixture  (for Selenium / test_sel.py)
# ─────────────────────────────────────────────

def _is_port_open(host="127.0.0.1", port=5000, timeout=1.0):
    """Return True if something is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=False)
def live_server():
    """
    Start a live Flask server on 127.0.0.1:5000 for Selenium tests.
    Uses an in-memory SQLite database so no real data is touched.
    This fixture is a no-op if a server is already listening on that port
    (e.g. you started it manually in a separate terminal).
    """
    if _is_port_open():
        yield  # already running externally
        return

    from app import app as sel_app, db as sel_db

    sel_app.config.update(
        TESTING=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="selenium-test-secret-key",
        SERVER_NAME=None,
    )

    with sel_app.app_context():
        sel_db.create_all()

    def _run():
        sel_app.run(host="127.0.0.1", port=5000, debug=False,
                    use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        if _is_port_open():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Live Flask server did not start within 10 seconds.")

    yield  # Selenium tests run here; daemon thread dies when session ends
