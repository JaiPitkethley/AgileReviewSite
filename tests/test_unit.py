"""
test_unit.py - Unit tests for the AgileReviewSite Flask application.

Coverage targets (from marking rubric):
  - User accounts  (signup, login, logout, duplicate detection)
  - Watchlist      (add, remove, priority toggle)
  - Library status (update status, favourites toggle)
  - Episode reviews (add, update, delete)
  - Friends        (add, remove, self-add guard)
  - Auth guard     (login_required decorator)
  - Helper functions (get_first_genre, get_genre_stats)

Run with:
    pytest tests/test_unit.py -v
"""

import pytest
from werkzeug.security import generate_password_hash

from app import (
    User,
    UserSeries,
    EpisodeReview,
    Favourite,
    Friendship,
    get_first_genre,
    get_genre_stats,
    db,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_user(db, username="alice", email="alice@example.com", password="pass123"):
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="alice@example.com", password="pass123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def make_series(db, user_id, tmdb_id=1, name="Test Show", status="watchlist"):
    s = UserSeries(
        user_id=user_id,
        tmdb_id=tmdb_id,
        name=name,
        genres="Drama, Action",
        status=status,
    )
    db.session.add(s)
    db.session.commit()
    return s


# ─────────────────────────────────────────────
# Helper function tests
# ─────────────────────────────────────────────

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

    def test_get_genre_stats(self, app):
        with app.app_context():
            shows = [
                UserSeries(user_id=1, tmdb_id=1, name="A", genres="Drama", status="watching"),
                UserSeries(user_id=1, tmdb_id=2, name="B", genres="Drama, Comedy", status="watching"),
                UserSeries(user_id=1, tmdb_id=3, name="C", genres="Comedy", status="watching"),
            ]
            stats = get_genre_stats(shows)
            assert stats["Drama"] == 2
            assert stats["Comedy"] == 1


# ─────────────────────────────────────────────
# User account tests
# ─────────────────────────────────────────────

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

    def test_login_wrong_password(self, client, db):
        make_user(db)
        resp = client.post(
            "/login",
            data={"email": "alice@example.com", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data

    def test_login_unknown_email(self, client, db):
        resp = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "pass"},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data

    def test_login_missing_fields(self, client, db):
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

    def test_delete_account_removes_user(self, auth_client, db):
        c, user = auth_client
        resp = c.post("/settings/delete-account", follow_redirects=True)
        assert resp.status_code == 200
        assert User.query.filter_by(id=user.id).first() is None


# ─────────────────────────────────────────────
# Auth guard / login_required tests
# ─────────────────────────────────────────────

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
    def test_protected_routes_redirect_unauthenticated(self, client, db, route):
        resp = client.get(route)
        # Should redirect (302) to login, not serve page content
        assert resp.status_code in (302, 301)
        assert "login" in resp.headers.get("Location", "").lower()


# ─────────────────────────────────────────────
# Watchlist tests
# ─────────────────────────────────────────────

class TestWatchlist:
    def test_watchlist_page_loads(self, auth_client):
        c, user = auth_client
        resp = c.get("/watchlist")
        assert resp.status_code == 200

    def test_remove_from_watchlist(self, auth_client, db):
        c, user = auth_client
        make_series(db, user.id, tmdb_id=10, status="watchlist")
        resp = c.post("/watchlist/remove", data={"tmdb_id": 10}, follow_redirects=True)
        assert resp.status_code == 200
        assert UserSeries.query.filter_by(user_id=user.id, tmdb_id=10, status="watchlist").first() is None

    def test_toggle_watchlist_priority_on(self, auth_client, db):
        c, user = auth_client
        s = make_series(db, user.id, tmdb_id=20, status="watchlist")
        assert s.priority is False
        c.post("/watchlist/priority", data={"tmdb_id": 20})
        db.session.refresh(s)
        assert s.priority is True

    def test_toggle_watchlist_priority_off(self, auth_client, db):
        c, user = auth_client
        s = make_series(db, user.id, tmdb_id=21, status="watchlist")
        s.priority = True
        db.session.commit()
        c.post("/watchlist/priority", data={"tmdb_id": 21})
        db.session.refresh(s)
        assert s.priority is False


# ─────────────────────────────────────────────
# Library / status tests
# ─────────────────────────────────────────────

class TestLibrary:
    def test_library_page_loads(self, auth_client, db):
        c, user = auth_client
        resp = c.get("/library")
        assert resp.status_code == 200

    def test_update_status_to_watching(self, auth_client, db):
        c, user = auth_client
        s = make_series(db, user.id, tmdb_id=30, status="watchlist")
        c.post("/series/status", data={"tmdb_id": 30, "status": "watching"}, follow_redirects=True)
        db.session.refresh(s)
        assert s.status == "watching"

    def test_update_status_to_completed(self, auth_client, db):
        c, user = auth_client
        s = make_series(db, user.id, tmdb_id=31, status="watching")
        c.post("/series/status", data={"tmdb_id": 31, "status": "completed"}, follow_redirects=True)
        db.session.refresh(s)
        assert s.status == "completed"

    def test_update_status_invalid_rejected(self, auth_client, db):
        c, user = auth_client
        s = make_series(db, user.id, tmdb_id=32, status="watching")
        c.post("/series/status", data={"tmdb_id": 32, "status": "hacked"}, follow_redirects=True)
        db.session.refresh(s)
        assert s.status == "watching"  # unchanged


# ─────────────────────────────────────────────
# Favourites tests
# ─────────────────────────────────────────────

class TestFavourites:
    def test_favourites_page_loads(self, auth_client):
        c, user = auth_client
        resp = c.get("/favourites")
        assert resp.status_code == 200

    def test_toggle_favourite_add(self, auth_client, db):
        c, user = auth_client
        make_series(db, user.id, tmdb_id=40, status="watching")
        c.post("/favourites/toggle", data={"tmdb_id": 40})
        fav = Favourite.query.filter_by(user_id=user.id, tmdb_id=40).first()
        assert fav is not None

    def test_toggle_favourite_remove(self, auth_client, db):
        c, user = auth_client
        make_series(db, user.id, tmdb_id=41, status="watching")
        fav = Favourite(user_id=user.id, tmdb_id=41, name="Show")
        db.session.add(fav)
        db.session.commit()
        c.post("/favourites/toggle", data={"tmdb_id": 41})
        assert Favourite.query.filter_by(user_id=user.id, tmdb_id=41).first() is None


# ─────────────────────────────────────────────
# Episode review tests
# ─────────────────────────────────────────────

class TestEpisodeReviews:
    """
    The /reviews/add endpoint only writes to the DB; it redirects to
    /series/<id>/season/<n>/episode/<n>/review which calls TMDB.
    We post WITHOUT follow_redirects to test the DB write, then check
    the redirect target separately.
    """

    def _post_review(self, client, series_id=1, season=1, episode=1, rating=8.0, text="Great episode!",
                     follow=False):
        return client.post(
            "/reviews/add",
            data={
                "series_id": series_id,
                "series_name": "Test Series",
                "season_number": season,
                "episode_number": episode,
                "episode_name": "Pilot",
                "episode_still_path": "",
                "rating": rating,
                "review_text": text,
            },
            follow_redirects=follow,
        )

    def test_add_review(self, auth_client, db):
        c, user = auth_client
        resp = self._post_review(c)
        # Should redirect (302) to the episode review page
        assert resp.status_code == 302
        review = EpisodeReview.query.filter_by(user_id=user.id, series_id=1).first()
        assert review is not None
        assert review.rating == 8.0
        assert review.review_text == "Great episode!"

    def test_add_review_empty_text_rejected(self, auth_client, db):
        c, user = auth_client
        resp = self._post_review(c, text="   ", follow=True)
        assert EpisodeReview.query.filter_by(user_id=user.id).first() is None

    def test_update_existing_review(self, auth_client, db):
        c, user = auth_client
        self._post_review(c, rating=5.0, text="Okay")
        self._post_review(c, rating=9.0, text="Actually amazing")
        reviews = EpisodeReview.query.filter_by(user_id=user.id, series_id=1).all()
        assert len(reviews) == 1
        assert reviews[0].rating == 9.0
        assert reviews[0].review_text == "Actually amazing"

    def test_delete_review(self, auth_client, db):
        c, user = auth_client
        # Insert review directly to avoid TMDB call
        review = EpisodeReview(
            user_id=user.id, series_id=1, series_name="S", season_number=1,
            episode_number=1, episode_name="E", rating=8.0, review_text="Good"
        )
        db.session.add(review)
        db.session.commit()
        review_id = review.id
        c.post(f"/reviews/{review_id}/delete", follow_redirects=False)
        assert EpisodeReview.query.filter_by(id=review_id).first() is None

    def test_review_stored_with_correct_fields(self, auth_client, db):
        c, user = auth_client
        resp = self._post_review(c, series_id=5, season=2, episode=3, rating=7.5, text="Solid writing")
        assert resp.status_code == 302
        review = EpisodeReview.query.filter_by(user_id=user.id).first()
        assert review.series_id == 5
        assert review.season_number == 2
        assert review.episode_number == 3
        assert review.rating == 7.5


# ─────────────────────────────────────────────
# Friends tests
# ─────────────────────────────────────────────

class TestFriends:
    def _make_second_user(self, db):
        return make_user(db, username="bob", email="bob@example.com")

    def test_friends_page_loads(self, auth_client):
        c, user = auth_client
        resp = c.get("/friends")
        assert resp.status_code == 200

    def test_add_friend(self, auth_client, db):
        c, user = auth_client
        bob = self._make_second_user(db)
        resp = c.post(f"/friends/add/{bob.username}", follow_redirects=True)
        assert resp.status_code == 200
        friendship = Friendship.query.filter_by(user_id=user.id, friend_id=bob.id).first()
        assert friendship is not None

    def test_cannot_add_self_as_friend(self, auth_client, db):
        c, user = auth_client
        resp = c.post(f"/friends/add/{user.username}", follow_redirects=False)
        # Flash is set and redirect happens; message appears on next page load
        # We verify via the session flash storage (follow redirect exposes it)
        resp2 = c.get("/friends")
        # Check no self-friendship was created
        self_friendship = Friendship.query.filter_by(
            user_id=user.id, friend_id=user.id
        ).first()
        assert self_friendship is None

    def test_cannot_add_duplicate_friend(self, auth_client, db):
        c, user = auth_client
        bob = self._make_second_user(db)
        c.post(f"/friends/add/{bob.username}", follow_redirects=True)
        # Second add should not create a second row
        c.post(f"/friends/add/{bob.username}", follow_redirects=True)
        count = Friendship.query.filter_by(user_id=user.id, friend_id=bob.id).count()
        assert count == 1

    def test_remove_friend(self, auth_client, db):
        c, user = auth_client
        bob = self._make_second_user(db)
        friendship = Friendship(user_id=user.id, friend_id=bob.id)
        db.session.add(friendship)
        db.session.commit()
        c.post(f"/friends/remove/{bob.username}", follow_redirects=True)
        assert Friendship.query.filter_by(user_id=user.id, friend_id=bob.id).first() is None

    def test_friend_profile_visible_to_friend(self, auth_client, db):
        c, user = auth_client
        bob = self._make_second_user(db)
        friendship = Friendship(user_id=user.id, friend_id=bob.id)
        db.session.add(friendship)
        db.session.commit()
        resp = c.get(f"/profile/{bob.username}")
        assert resp.status_code == 200

    def test_non_friend_profile_blocked(self, auth_client, db):
        c, user = auth_client
        bob = self._make_second_user(db)
        # Should redirect away from bob's profile (not 200 with profile content)
        resp = c.get(f"/profile/{bob.username}", follow_redirects=False)
        assert resp.status_code == 302
        assert "friends" in resp.headers.get("Location", "")


# ─────────────────────────────────────────────
# Database model constraint tests
# ─────────────────────────────────────────────

class TestDatabaseConstraints:
    def test_unique_user_episode_review(self, auth_client, db):
        """Duplicate (user, series, season, episode) should not create a second row."""
        from sqlalchemy.exc import IntegrityError
        c, user = auth_client
        r1 = EpisodeReview(
            user_id=user.id, series_id=1, series_name="S", season_number=1,
            episode_number=1, episode_name="E", rating=7.0, review_text="First"
        )
        db.session.add(r1)
        db.session.commit()
        r2 = EpisodeReview(
            user_id=user.id, series_id=1, series_name="S", season_number=1,
            episode_number=1, episode_name="E", rating=9.0, review_text="Second"
        )
        db.session.add(r2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_unique_user_series(self, auth_client, db):
        """A user cannot add the same TMDB show twice."""
        from sqlalchemy.exc import IntegrityError
        c, user = auth_client
        make_series(db, user.id, tmdb_id=99)
        s2 = UserSeries(user_id=user.id, tmdb_id=99, name="Duplicate", status="watching")
        db.session.add(s2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_password_is_hashed_not_plaintext(self, db, client):
        client.post(
            "/signup",
            data={"username": "secured", "email": "secured@example.com", "password": "myplainpassword"},
        )
        user = User.query.filter_by(email="secured@example.com").first()
        assert "myplainpassword" not in user.password_hash

    def test_user_relationships_cascade_delete(self, auth_client, db):
        """Deleting a user should remove their reviews and series entries."""
        c, user = auth_client
        make_series(db, user.id)
        r = EpisodeReview(
            user_id=user.id, series_id=1, series_name="S", season_number=1,
            episode_number=1, episode_name="E", rating=8.0, review_text="Good"
        )
        db.session.add(r)
        db.session.commit()

        user_obj = User.query.get(user.id)
        db.session.delete(user_obj)
        db.session.commit()

        assert EpisodeReview.query.filter_by(user_id=user.id).count() == 0
        assert UserSeries.query.filter_by(user_id=user.id).count() == 0
