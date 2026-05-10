from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

## database + API imports
from flask_sqlalchemy import SQLAlchemy
import requests

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "users.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-before-sharing"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

## SQLAlchemy configuration (SQLite file stored locally)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(DATABASE)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

## Users table
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    series = db.relationship("UserSeries", backref="user", lazy=True)

class UserSeries(db.Model):
    __tablename__ = "user_series"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tmdb_id = db.Column(db.Integer, nullable=False)

    name = db.Column(db.String(200), nullable=False)
    poster_path = db.Column(db.String(300), nullable=True)
    vote_average = db.Column(db.Float, nullable=True)

    # Stores genres as text like: "Comedy, Drama, Sci-Fi"
    genres = db.Column(db.String(300), nullable=True)

    # Main status system
    # watchlist, watching, completed, on_hold, dropped
    status = db.Column(db.String(30), nullable=False, default="watchlist")

    priority = db.Column(db.Boolean, default=False)

    added_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("user_id", "tmdb_id", name="uq_user_tmdb"),
    )

TMDB_API_KEY = "ac9052cb2ef122c333a96cb6540a5e2b"
TMDB_READ_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhYzkwNTJjYjJlZjEyMmMzMzNhOTZjYjY1NDBhNWUyYiIsIm5iZiI6MTc3NDU5OTgwNy4wOTYsInN1YiI6IjY5YzYzZTdmMDJhY2FmNTM5YzAzZDQyZiIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.l1ow7B1d7yYGAlicNMAO6ucy-aTdspSkExaF49KDmFU"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

def get_show_details(tmdb_id):
    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}"
    response = requests.get(url)
    data = response.json()
    return data
def get_genre_stats(shows):
    stats = {}

    for show in shows:
        if not show.genres:
            continue

def get_first_genre(show):
    if not show.genres:
        return None

    return show.genres.split(",")[0].strip()


def get_genre_stats(shows):
    stats = {}

    for show in shows:
        genre = get_first_genre(show)

        if genre:
            stats[genre] = stats.get(genre, 0) + 1

    return dict(sorted(stats.items(), key=lambda item: item[1], reverse=True))


def get_status_genre_stats(shows):
    stats = {}

    for show in shows:
        status = show.status

        if status not in stats:
            stats[status] = {}

        genre = get_first_genre(show)

        if genre:
            stats[status][genre] = stats[status].get(genre, 0) + 1

    return stats

    return dict(sorted(stats.items(), key=lambda item: item[1], reverse=True))


def get_status_genre_stats(shows):
    stats = {}

    for show in shows:
        status = show.status

        if status not in stats:
            stats[status] = {}

        if show.genres:
            first_genere = show.genres.split(",")[0].strip()

            if first_genere:
                stats[status][first_genere] = stats[status].get(first_genere, 0) + 1

    return stats

## load logged in user
@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = User.query.with_entities(User.id, User.username, User.email).filter_by(id=user_id).first()

## login required decorator
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
@app.route("/series/<int:series_id>")
def series_detail(series_id):
    url = f"https://api.themoviedb.org/3/tv/{series_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }

    response = requests.get(url, params=params)
    series = response.json()

    return render_template("seriesdetail.html", series=series, user=g.user)

@app.route("/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        return redirect(request.referrer or url_for("dashboard"))

    tmdb_id = int(tmdb_id)

    existing = UserSeries.query.filter_by(
        user_id=g.user.id,
        tmdb_id=tmdb_id
    ).first()

    if existing:
        existing.status = "watchlist"
        db.session.commit()
        return redirect(request.referrer or url_for("watchlist"))

    show = get_show_details(tmdb_id)

    genre_names = []
    for genre in show.get("genres", []):
        genre_names.append(genre.get("name"))

    entry = UserSeries(
        user_id=g.user.id,
        tmdb_id=tmdb_id,
        name=show.get("name", "Unknown Series"),
        poster_path=show.get("poster_path"),
        vote_average=show.get("vote_average"),
        genres=", ".join(genre_names),
        status="watchlist"
    )

    db.session.add(entry)
    db.session.commit()

    return redirect(request.referrer or url_for("watchlist"))
def remove_from_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if tmdb_id:
        UserSeries.query.filter_by(
            user_id=g.user.id,
            tmdb_id=int(tmdb_id)
        ).delete()
        db.session.commit()

    return redirect(request.referrer or url_for("watchlist"))
@login_required
def remove_from_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    Watchlist.query.filter_by(user_id=g.user.id, tmdb_id=int(tmdb_id)).delete()
    db.session.commit()

    # flash("Removed from your watchlist.", "success")
    return redirect(request.referrer or url_for("dashboard"))
@app.route("/series/status", methods=["POST"])
@login_required
def update_series_status():
    tmdb_id = request.form.get("tmdb_id")
    status = request.form.get("status")

    allowed_statuses = ["watchlist", "watching", "completed", "on_hold", "dropped"]

    if not tmdb_id or status not in allowed_statuses:
        return redirect(request.referrer or url_for("library"))

    item = UserSeries.query.filter_by(
        user_id=g.user.id,
        tmdb_id=int(tmdb_id)
    ).first()

    if item:
        item.status = status
        db.session.commit()

    return redirect(request.referrer or url_for("library"))
@app.route("/watchlist")
@login_required
def watchlist():
    shows = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="watchlist"
    ).all()

    genre_stats = get_genre_stats(shows)

    return render_template(
        "watchlist.html",
        shows=shows,
        user=g.user,
        genre_stats=genre_stats
    )
    
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))

## Real logged-in pages

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=g.user)


@app.route("/library")
@login_required
def library():
    shows = UserSeries.query.filter(
        UserSeries.user_id == g.user.id,
        UserSeries.status.in_(["watching", "completed", "on_hold", "dropped"])
    ).all()

    total_series = len(shows)
    completed_count = sum(1 for show in shows if show.status == "completed")
    watching_count = sum(1 for show in shows if show.status == "watching")
    dropped_count = sum(1 for show in shows if show.status == "dropped")
    on_hold_count = sum(1 for show in shows if show.status == "on_hold")

    genre_stats = get_genre_stats(shows)
    status_genre_stats = get_status_genre_stats(shows)

    return render_template(
        "library.html",
        user=g.user,
        shows=shows,
        total_series=total_series,
        completed_count=completed_count,
        watching_count=watching_count,
        dropped_count=dropped_count,
        on_hold_count=on_hold_count,
        genre_stats=genre_stats,
        status_genre_stats=status_genre_stats
    )


@app.route("/favourites")
@login_required
def favourites():
    return render_template("favourites.html", user=g.user)


@app.route("/community")
@login_required
def community():
    return render_template("community.html", user=g.user)


@app.route("/friends")
@login_required
def friends():
    return render_template("friends.html", user=g.user)


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=g.user)

@app.route("/series/<int:series_id>/season/<int:season_number>/episode/<int:episode_number>/review")
def review_episode(series_id, season_number, episode_number):
    episode_url = f"{TMDB_BASE_URL}/tv/{series_id}/season/{season_number}/episode/{episode_number}"

    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }

    episode = requests.get(episode_url, params=params).json()

    return render_template("reviewepisode.html", episode=episode, series_id=series_id)

@app.route("/series/<int:series_id>/season/<int:season_number>")
def season_detail(series_id, season_number):
    series_url = f"{TMDB_BASE_URL}/tv/{series_id}"
    season_url = f"{TMDB_BASE_URL}/tv/{series_id}/season/{season_number}"

    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }

    series_response = requests.get(series_url, params=params)
    season_response = requests.get(season_url, params=params)

    series = series_response.json()
    season = season_response.json()

    return render_template("seasondetail.html", series=series, season=season, user=g.user)
    


if __name__ == "__main__":
    ## create tables if they do not exist
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    
