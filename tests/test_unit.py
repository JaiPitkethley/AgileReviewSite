"""
test_unit.py — Unit tests for the AgileReviewSite Flask application.

Coverage
--------
  - Helper functions  (get_first_genre, get_genre_stats)
  - User accounts     (signup, login, logout, duplicate detection)
  - Auth guard        (login_required on all protected routes)
  - DB constraints    (password hashing)

Run with:
    pytest tests/test_unit.py -v
"""

import pytest
from werkzeug.security import generate_password_hash

from app import (
    User,
    UserSeries,
    get_first_genre,
    get_genre_stats,
    db,
)


# ─────────────────────────────────────────────────────────────────
# Test data factories
# ─────────────────────────────────────────────────────────────────

def make_user(db, username="alice", email="alice@example.com", password="pass123"):
    """Insert a User row and return the instance."""
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="alice@example.com", password="pass123"):
    """POST to /login and follow redirects."""
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ─────────────────────────────────────────────────────────────────
# Helper function tests
# ─────────────────────────────────────────────────────────────────

class TestHelpers:

    def test_get_first_genre_single(self, app):
        with app.app_context():
            show = UserSeries(user_id=1, tmdb_id=99, name="X", genres="Comedy", status="watching")
            assert get_first_genre(show) == "Comedy"

    def test_get_first_genre_multiple(self, app):
        with app.app_context():
            show = UserSeries(user_id=1, tmdb_id=99, name="X", genres="Drama, Thriller", status="watching")
            assert get_first_genre(show) == "Drama"

    def test_get_first_genre_none(self, app):
        with app.app_context():
            show = UserSeries(user_id=1, tmdb_id=99, name="X", genres=None, status="watching")
            assert get_first_genre(show) is None

    def test_get_genre_stats_counts_first_genre_only(self, app):
        """
        get_genre_stats counts only the first genre per show (via get_first_genre).
        A show with genres="Drama, Comedy" contributes 1 to Drama, not to Comedy.
        """
        with app.app_context():
            shows = [
                UserSeries(user_id=1, tmdb_id=1, name="A", genres="Drama",        status="watching"),
                UserSeries(user_id=1, tmdb_id=2, name="B", genres="Drama, Comedy", status="watching"),
                UserSeries(user_id=1, tmdb_id=3, name="C", genres="Comedy",        status="watching"),
            ]
            stats = get_genre_stats(shows)

            # Drama is the first genre of shows A and B
            assert stats["Drama"] == 2
            # Comedy is the first genre of show C only (show B's Comedy is not counted)
            assert stats["Comedy"] == 1
            # No other genres should be present
            assert set(stats.keys()) == {"Drama", "Comedy"}

    def test_get_genre_stats_empty_list(self, app):
        with app.app_context():
            assert get_genre_stats([]) == {}

    def test_get_genre_stats_all_none_genres(self, app):
        with app.app_context():
            shows = [
                UserSeries(user_id=1, tmdb_id=1, name="A", genres=None, status="watching"),
            ]
            assert get_genre_stats(shows) == {}


# ─────────────────────────────────────────────────────────────────
# User account tests
# ─────────────────────────────────────────────────────────────────

class TestUserAccounts:

    def test_signup_creates_user(self, client, db):
        resp = client.post(
            "/signup",
            data={"username": "newuser", "email": "new@example.com", "password": "securepass"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        user = User.query.filter_by(email="new@example.com").first()
        assert user is not None
        assert user.username == "newuser"

    def test_signup_hashes_password(self, client, db):
        client.post(
            "/signup",
            data={"username": "hashed", "email": "hashed@example.com", "password": "plaintext"},
        )
        user = User.query.filter_by(email="hashed@example.com").first()
        assert user.password_hash != "plaintext"

    def test_signup_duplicate_email_rejected(self, client, db):
        make_user(db)
        resp = client.post(
            "/signup",
            data={"username": "alice2", "email": "alice@example.com", "password": "pass"},
            follow_redirects=True,
        )
        assert b"already registered" in resp.data

    def test_signup_duplicate_username_rejected(self, client, db):
        make_user(db)
        resp = client.post(
            "/signup",
            data={"username": "alice", "email": "different@example.com", "password": "pass"},
            follow_redirects=True,
        )
        assert b"already taken" in resp.data

    def test_signup_missing_fields_rejected(self, client, db):
        resp = client.post(
            "/signup",
            data={"username": "", "email": "", "password": ""},
            follow_redirects=True,
        )
        assert b"required" in resp.data

    def test_login_success(self, client, db):
        make_user(db)
        resp = login(client)
        assert resp.status_code == 200

    def test_login_wrong_password_shows_error(self, client, db):
        make_user(db)
        resp = client.post(
            "/login",
            data={"email": "alice@example.com", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data

    def test_login_unknown_email_shows_error(self, client, db):
        resp = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "pass"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data

    def test_login_missing_fields_shows_error(self, client, db):
        resp = client.post(
            "/login",
            data={"email": "", "password": ""},
            follow_redirects=True,
        )
        assert b"Please enter" in resp.data

    def test_logout_clears_session(self, client, db):
        make_user(db)
        login(client)
        resp = client.get("/logout", follow_redirects=True)
        assert b"signed out" in resp.data


# ─────────────────────────────────────────────────────────────────
# Auth guard / login_required tests
# ─────────────────────────────────────────────────────────────────

class TestAuthGuard:

    @pytest.mark.parametrize("route", [
        "/dashboard",
        "/profile",
        "/library",
        "/watchlist",
        "/favourites",
        "/friends",
        "/stats",
        "/settings",
    ])
    def test_protected_route_redirects_unauthenticated(self, client, db, route):
        resp = client.get(route)
        assert resp.status_code in (301, 302)
        assert "login" in resp.headers.get("Location", "").lower()


# ─────────────────────────────────────────────────────────────────
# Database model constraint tests
# ─────────────────────────────────────────────────────────────────

class TestDatabaseConstraints:

    def test_password_stored_as_hash(self, client, db):
        client.post(
            "/signup",
            data={"username": "secured", "email": "secured@example.com", "password": "myplainpassword"},
        )
        user = User.query.filter_by(email="secured@example.com").first()
        assert "myplainpassword" not in user.password_hash
