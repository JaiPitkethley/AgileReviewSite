"""
conftest.py — Shared pytest fixtures for unit and Selenium tests.

Uses a separate in-memory SQLite database so the production database is
never touched.  All fixtures are Python 3.12 / SQLAlchemy 2.x compatible.

Key design decisions
--------------------
* WTF_CSRF_ENABLED=False AND WTF_CSRF_CHECK_DEFAULT=False are both required:
  the first disables the hidden-field check; the second stops CSRFProtect
  (already bound to the app at import time) from running protect() at all.

* SERVER_NAME is intentionally omitted from the unit-test app config.
  Flask 2+ requires every test-client request's Host header to match
  SERVER_NAME exactly; a mismatch causes a 404 on every route.

* The db fixture drops and recreates all tables before each test.
  This is the most reliable isolation strategy for Flask-SQLAlchemy 2.x
  with an in-memory SQLite database — it avoids all session-binding and
  savepoint complexity, and guarantees every test starts with a clean slate.
"""

import os
import time
import socket
import threading

import pytest

# Environment variables must be set before the app module is imported so
# that app.py picks them up when it calls os.getenv().
os.environ.setdefault("SECRET_KEY",      "test-secret-key-not-for-production")
os.environ.setdefault("TMDB_API_KEY",    "test_api_key")
os.environ.setdefault("TMDB_READ_TOKEN", "test_read_token")

from app import app as flask_app, db as _db  # noqa: E402 (must follow env setup)


# ─────────────────────────────────────────────────────────────────
# Unit-test fixtures
# ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Flask application configured for testing with an isolated in-memory DB.

    Scoped to the session so the same app object is reused across all tests.
    The in-memory URI ensures the real users.db on disk is never touched.
    """
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        WTF_CSRF_CHECK_DEFAULT=False,
    )
    yield flask_app


@pytest.fixture(scope="function")
def db(app):
    """
    Provide a clean database for every test.

    Drops all tables then recreates them before each test, guaranteeing a
    completely empty schema regardless of what the previous test did.
    Tears down by dropping all tables again to free memory.
    """
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """Flask test client backed by a fresh per-test database."""
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="function")
def auth_client(client, db):
    """
    Flask test client that is already logged in as a standard test user.

    Returns (client, user) so tests can reference the user object directly.
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


# ─────────────────────────────────────────────────────────────────
# Live-server fixture (used by test_selenium.py)
# ─────────────────────────────────────────────────────────────────

def _is_port_open(host="127.0.0.1", port=5000, timeout=1.0):
    """Return True if a process is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=False)
def live_server():
    """
    Start a live Flask server on 127.0.0.1:5000 for Selenium tests.

    Uses an isolated in-memory SQLite database so no real data is touched.
    If a server is already listening on port 5000 (e.g. started manually
    in a separate terminal) this fixture simply yields immediately without
    starting a second instance.
    """
    if _is_port_open():
        yield
        return

    from app import app as sel_app, db as sel_db

    sel_app.config.update(
        TESTING=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        WTF_CSRF_CHECK_DEFAULT=False,
        SECRET_KEY="selenium-test-secret-key",
        SERVER_NAME=None,
    )

    with sel_app.app_context():
        sel_db.create_all()

    def _run():
        sel_app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        if _is_port_open():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Live Flask server did not start within 10 seconds.")

    yield  # tests run here; daemon thread is stopped when the session ends
