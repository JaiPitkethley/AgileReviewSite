from datetime import timedelta
from functools import wraps
from pathlib import Path
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "users.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-before-sharing"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)

    # Users table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Watchlist table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tmdb_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, tmdb_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    conn.commit()
    conn.close()

import requests

TMDB_API_KEY = "YOUR_API_KEY_HERE"

def get_show_details(tmdb_id):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}"
    response = requests.get(url)
    return response.json()


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT id, username, email FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please sign in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.route("/")
def index():
    return redirect(url_for("landing"))


@app.route("/landing")
def landing():
    prefill_email = request.args.get("email", "")
    if g.user is not None:
        prefill_email = g.user["email"]
    return render_template("landing.html", prefill_email=prefill_email)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    prefill_email = request.args.get("email", "")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("signup.html", prefill_email=email)

        db = get_db()
        existing_user = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user is not None:
            flash("That email is already registered. Please sign in instead.", "error")
            return render_template("signup.html", prefill_email=email)

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")

        cursor = db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash)
        )
        db.commit()

        session.clear()
        session["user_id"] = cursor.lastrowid
        session.permanent = True

        flash("Account created successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html", prefill_email=prefill_email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html")

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True

        flash("Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("reviewsitehome.html", user=g.user)

@app.route("/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        flash("Invalid show.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO watchlist (user_id, tmdb_id) VALUES (?, ?)",
            (g.user["id"], tmdb_id)
        )
        db.commit()
        flash("Added to your watchlist.", "success")
    except sqlite3.IntegrityError:
        flash("Already in your watchlist.", "info")

    return redirect(request.referrer or url_for("dashboard"))

@app.route("/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    db = get_db()
    db.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND tmdb_id = ?",
        (g.user["id"], tmdb_id)
    )
    db.commit()

    flash("Removed from your watchlist.", "success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/watchlist")
@login_required
def watchlist():
    db = get_db()
    items = db.execute(
        "SELECT tmdb_id FROM watchlist WHERE user_id = ?",
        (g.user["id"],)
    ).fetchall()

    shows = []
    for item in items:
        show = get_show_details(item["tmdb_id"])
        shows.append(show)

    return render_template("watchlist.html", shows=shows, user=g.user)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))

## dummy part for development, to be replaced with real user data and functionality later
## Dashboard
@app.route("/d/dashboard")
def d_dashboard():
    return render_template("reviewsitehome.html", user={"username": "James"})


## Profile
@app.route("/d/profile")
def d_profile():
    return render_template("profile.html", user={"username": "James"})


## My Library
@app.route("/d/library")
def d_library():
    return render_template("library.html", user={"username": "James"})


## Watchlist
@app.route("/d/watchlist")
def d_watchlist():
    return render_template("watchlist.html", user={"username": "James"})


## Favourites
@app.route("/d/favourites")
def d_favourites():
    return render_template("favourites.html", user={"username": "James"})


## Community
@app.route("/d/community")
def d_community():
    return render_template("community.html", user={"username": "James"})


## Friends
@app.route("/d/friends")
def d_friends():
    return render_template("friends.html", user={"username": "James"})


## Settings
@app.route("/d/settings")
def d_settings():
    return render_template("settings.html", user={"username": "James"})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)