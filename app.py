from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# database + API imports
from flask_sqlalchemy import SQLAlchemy
import requests

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "users.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-before-sharing"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# SQLAlchemy configuration (SQLite file stored locally)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(DATABASE)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Users table
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    watchlist = db.relationship("Watchlist", backref="user", lazy=True)


# Watchlist table
class Watchlist(db.Model):
    __tablename__ = "watchlist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tmdb_id = db.Column(db.Integer, nullable=False)
    added_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("user_id", "tmdb_id", name="uq_user_tmdb"),
    )


# here is where our api keys will go, make sure not to push the real ones
TMDB_API_KEY = "key goes here"
TMDB_READ_TOKEN = "read token goes here"


def get_show_details(tmdb_id):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def search_tv_series(query):
    url = "https://api.themoviedb.org/3/search/tv"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "include_adult": "false",
        "language": "en-US",
        "page": 1
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


# load logged in user
@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = User.query.with_entities(
            User.id,
            User.username,
            User.email
        ).filter_by(id=user_id).first()


# login required decorator
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
        prefill_email = g.user.email
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

        existing_user = User.query.filter_by(email=email).first()

        if existing_user is not None:
            flash("That email is already registered. Please sign in instead.", "error")
            return render_template("signup.html", prefill_email=email)

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")

        user = User(username=username, email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()

        session.clear()
        session["user_id"] = user.id
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

        user = User.query.filter_by(email=email).first()

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user.id
        session.permanent = True

        flash("Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("reviewsitehome.html", user=g.user)


@app.route("/api/search")
@login_required
def api_search():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"results": []})

    try:
        results = search_tv_series(query)
        return jsonify({"results": results})
    except requests.RequestException:
        return jsonify({"results": [], "error": "Failed to fetch search results"}), 500


@app.route("/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        flash("Invalid show.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    try:
        entry = Watchlist(user_id=g.user.id, tmdb_id=int(tmdb_id))
        db.session.add(entry)
        db.session.commit()
        flash("Added to your watchlist.", "success")
    except Exception:
        db.session.rollback()
        flash("Already in your watchlist.", "info")

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        flash("Invalid show.", "error")
        return redirect(request.referrer or url_for("watchlist"))

    Watchlist.query.filter_by(user_id=g.user.id, tmdb_id=int(tmdb_id)).delete()
    db.session.commit()

    flash("Removed from your watchlist.", "success")
    return redirect(request.referrer or url_for("watchlist"))


@app.route("/watchlist")
@login_required
def watchlist():
    items = Watchlist.query.filter_by(user_id=g.user.id).all()

    shows = []
    for item in items:
        try:
            show = get_show_details(item.tmdb_id)
            shows.append(show)
        except requests.RequestException:
            continue

    return render_template("watchlist.html", shows=shows, user=g.user)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


# dummy part for development, to be replaced with real user data and functionality later
# Dashboard
@app.route("/d/dashboard")
def d_dashboard():
    return render_template("reviewsitehome.html", user={"username": "James"})


# Profile
@app.route("/d/profile")
def d_profile():
    return render_template("profile.html", user={"username": "James"})


# My Library
@app.route("/d/library")
def d_library():
    return render_template("library.html", user={"username": "James"})


# Watchlist
@app.route("/d/watchlist")
def d_watchlist():
    return render_template("watchlist.html", user={"username": "James"})


# Favourites
@app.route("/d/favourites")
def d_favourites():
    return render_template("favourites.html", user={"username": "James"})


# Community
@app.route("/d/community")
def d_community():
    return render_template("community.html", user={"username": "James"})


# Friends
@app.route("/d/friends")
def d_friends():
    return render_template("friends.html", user={"username": "James"})


# Settings
@app.route("/d/settings")
def d_settings():
    return render_template("settings.html", user={"username": "James"})


if __name__ == "__main__":
    # create tables if they do not exist
    with app.app_context():
        db.create_all()
    app.run(debug=True)