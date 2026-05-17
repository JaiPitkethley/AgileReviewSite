from datetime import datetime, timedelta
from collections import Counter, defaultdict
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import requests

from dotenv import load_dotenv
import os

from flask_wtf import CSRFProtect


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "users.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(DATABASE)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
csrf = CSRFProtect(app)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TRACKED_STATUSES = ["watchlist", "watching", "completed", "on_hold", "dropped"]


# -------------------- MODELS --------------------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    series = db.relationship("UserSeries", backref="user", lazy=True, cascade="all, delete-orphan")
    episode_reviews = db.relationship("EpisodeReview", backref="user", lazy=True, cascade="all, delete-orphan")
    favourites = db.relationship("Favourite", backref="user", lazy=True, cascade="all, delete-orphan")


class UserSeries(db.Model):
    __tablename__ = "user_series"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tmdb_id = db.Column(db.Integer, nullable=False)

    name = db.Column(db.String(200), nullable=False)
    poster_path = db.Column(db.String(300), nullable=True)
    vote_average = db.Column(db.Float, nullable=True)
    genres = db.Column(db.String(300), nullable=True)

    # watchlist, watching, completed, on_hold, dropped
    status = db.Column(db.String(30), nullable=False, default="watchlist")
    priority = db.Column(db.Boolean, default=False)
    added_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("user_id", "tmdb_id", name="uq_user_tmdb"),
    )

review_likes = db.Table(
    "review_likes",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("review_id", db.Integer, db.ForeignKey("episode_reviews.id"), primary_key=True),
)

comment_likes = db.Table(
    "comment_likes",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("comment_id", db.Integer, db.ForeignKey("comments.id"), primary_key=True),
)

class EpisodeReview(db.Model):
    __tablename__ = "episode_reviews"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    series_id = db.Column(db.Integer, nullable=False)
    series_name = db.Column(db.String(200), nullable=False)

    season_number = db.Column(db.Integer, nullable=False)
    episode_number = db.Column(db.Integer, nullable=False)
    episode_name = db.Column(db.String(200), nullable=False)
    episode_still_path = db.Column(db.String(300), nullable=True)

    rating = db.Column(db.Float, nullable=False)
    review_text = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "series_id",
            "season_number",
            "episode_number",
            name="uq_user_episode_review"
        ),
    )

    comments = db.relationship("Comment", backref="review", lazy="dynamic")

    liked_by = db.relationship(
        "User",
        secondary=review_likes,
        backref=db.backref("liked_reviews", lazy="dynamic"),
        lazy="dynamic",
    )

    @property
    def like_count(self):
        return self.liked_by.count()


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    review_id = db.Column(db.Integer, db.ForeignKey("episode_reviews.id"), nullable=False)

    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    user = db.relationship("User", backref="comments", lazy=True)

    liked_by = db.relationship(
        "User",
        secondary=comment_likes,
        backref=db.backref("liked_comments", lazy="dynamic"),
        lazy="dynamic",
    )

    @property
    def like_count(self):
        return self.liked_by.count()


class Favourite(db.Model):
    __tablename__ = "favourites"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tmdb_id = db.Column(db.Integer, nullable=False)

    name = db.Column(db.String(200), nullable=False)
    poster_path = db.Column(db.String(300), nullable=True)
    vote_average = db.Column(db.Float, nullable=True)
    added_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("user_id", "tmdb_id", name="uq_user_favourite_tmdb"),
    )

class Friendship(db.Model):
    __tablename__ = "friendships"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("friendships", cascade="all, delete-orphan")
    )

    friend = db.relationship(
        "User",
        foreign_keys=[friend_id]
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "friend_id", name="uq_user_friend"),
    )
# -------------------- HELPERS --------------------

def get_show_details(tmdb_id):
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    return response.json()
def get_or_create_user_series(tmdb_id, default_status="watchlist"):
    item = UserSeries.query.filter_by(
        user_id=g.user.id,
        tmdb_id=tmdb_id
    ).first()

    if item:
        return item

    show = get_show_details(tmdb_id)

    genre_names = []
    for genre in show.get("genres", []):
        if genre.get("name"):
            genre_names.append(genre.get("name"))

    item = UserSeries(
        user_id=g.user.id,
        tmdb_id=tmdb_id,
        name=show.get("name", "Unknown Series"),
        poster_path=show.get("poster_path"),
        vote_average=show.get("vote_average"),
        genres=", ".join(genre_names),
        status=default_status
    )

    db.session.add(item)
    db.session.flush()

    return item

def fetch_tmdb(endpoint, params=None):
    if not TMDB_API_KEY:
        return []

    url = f"{TMDB_BASE_URL}/{endpoint}"
    query = {"api_key": TMDB_API_KEY, "language": "en-US"}
    if params:
        query.update(params)

    try:
        response = requests.get(url, params=query, timeout=5)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.RequestException:
        return []


def format_tmdb_card(show, badge=None):
    title = show.get("name") or show.get("title") or "Untitled"
    poster_path = show.get("poster_path") or show.get("backdrop_path") or ""
    rating = show.get("vote_average") or 0
    first_air = show.get("first_air_date") or show.get("release_date") or ""
    year = first_air[:4] if first_air else ""
    subtitle = f"TV · {year}" if year else "TV"
    star_count = min(5, max(0, int(round(rating / 2))))
    stars = "★" * star_count + "☆" * (5 - star_count)

    return {
        "tmdb_id": show.get("id"),
        "title": title,
        "poster_path": poster_path,
        "rating": rating,
        "subtitle": subtitle,
        "stars": stars,
        "badge": badge,
        "progress_width": min(100, max(0, int(rating * 10))),
        "initial": title[:1].upper() if title else "T",
    }


def get_tmdb_trending(limit=6):
    shows = fetch_tmdb("trending/tv/week", {"page": 1})
    return [format_tmdb_card(show, badge="Trending") for show in shows[:limit]]


def get_tmdb_new_releases(limit=6):
    shows = fetch_tmdb("tv/airing_today", {"page": 1})
    return [format_tmdb_card(show, badge="New") for show in shows[:limit]]


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
        genre = get_first_genre(show)

        if status not in stats:
            stats[status] = {}

        if genre:
            stats[status][genre] = stats[status].get(genre, 0) + 1

    return stats


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please sign in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


# -------------------- AUTH / SESSION --------------------

@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = User.query.get(user_id)


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
        
        existing_username = User.query.filter_by(username=username).first()
        if existing_username is not None:
            flash("That username is already taken. Please choose another one.", "error")
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


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


# -------------------- MAIN PAGES --------------------

@app.route("/dashboard")
@login_required
def dashboard():
    total_series = UserSeries.query.filter_by(user_id=g.user.id).count()
    watchlist_count = UserSeries.query.filter_by(user_id=g.user.id, status="watchlist").count()
    watching_count = UserSeries.query.filter_by(user_id=g.user.id, status="watching").count()
    completed_count = UserSeries.query.filter_by(user_id=g.user.id, status="completed").count()
    episode_count = EpisodeReview.query.filter_by(user_id=g.user.id).count()

    continue_watching = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="watching"
    ).order_by(UserSeries.added_at.desc()).limit(3).all()

    if not continue_watching:
        continue_watching = UserSeries.query.filter_by(
            user_id=g.user.id
        ).order_by(UserSeries.added_at.desc()).limit(3).all()

    trending_shows = get_tmdb_trending()
    new_releases = get_tmdb_new_releases()

    return render_template(
        "reviewsitehome.html",
        user=g.user,
        total_series=total_series,
        watchlist_count=watchlist_count,
        watching_count=watching_count,
        completed_count=completed_count,
        episode_count=episode_count,
        continue_watching=continue_watching,
        trending_shows=trending_shows,
        new_releases=new_releases,
    )


@app.route("/profile")
@login_required
def profile():
    recent_reviews = EpisodeReview.query.filter_by(
        user_id=g.user.id
    ).order_by(
        EpisodeReview.created_at.desc()
    ).limit(10).all()

    review_count = EpisodeReview.query.filter_by(
        user_id=g.user.id
    ).count()

    watchlist_count = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="watchlist"
    ).count()

    completed_count = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="completed"
    ).count()

    watching_count = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="watching"
    ).count()

    episodes_tracked_count = EpisodeReview.query.filter_by(
        user_id=g.user.id
    ).count()

    favourite_items = (
        db.session.query(UserSeries)
        .join(Favourite, Favourite.tmdb_id == UserSeries.tmdb_id)
        .filter(
            UserSeries.user_id == g.user.id,
            Favourite.user_id == g.user.id,
            UserSeries.status.in_(TRACKED_STATUSES)
        )
        .order_by(Favourite.added_at.desc())
        .limit(4)
        .all()
    )

    poster_paths = {}

    for review in recent_reviews:
        if review.series_id not in poster_paths:
            series = get_show_details(review.series_id)
            poster_paths[review.series_id] = series.get("poster_path")

    return render_template(
        "profile.html",
        user=g.user,
        recent_reviews=recent_reviews,
        review_count=review_count,
        watchlist_count=watchlist_count,
        completed_count=completed_count,
        watching_count=watching_count,
        episodes_tracked_count=episodes_tracked_count,
        favourite_items=favourite_items,
        poster_paths=poster_paths
    )
@app.route("/profile/<username>")
@login_required
def public_profile(username):
    profile_user = User.query.filter_by(username=username).first_or_404()

    is_friend = Friendship.query.filter_by(
        user_id=g.user.id,
        friend_id=profile_user.id
    ).first() is not None

    if profile_user.id != g.user.id and not is_friend:
        flash("You can only view profiles of your friends.", "error")
        return redirect(url_for("friends"))

    recent_reviews = EpisodeReview.query.filter_by(
        user_id=profile_user.id
    ).order_by(
        EpisodeReview.created_at.desc()
    ).limit(10).all()

    review_count = EpisodeReview.query.filter_by(
        user_id=profile_user.id
    ).count()

    watchlist_count = UserSeries.query.filter_by(
        user_id=profile_user.id,
        status="watchlist"
    ).count()

    watching_count = UserSeries.query.filter_by(
        user_id=profile_user.id,
        status="watching"
    ).count()

    completed_count = UserSeries.query.filter_by(
        user_id=profile_user.id,
        status="completed"
    ).count()

    poster_paths = {}

    for review in recent_reviews:
        if review.series_id not in poster_paths:
            series = get_show_details(review.series_id)
            poster_paths[review.series_id] = series.get("poster_path")

    return render_template(
        "friendprofile.html",
        profile_user=profile_user,
        user=g.user,
        recent_reviews=recent_reviews,
        review_count=review_count,
        watchlist_count=watchlist_count,
        watching_count=watching_count,
        completed_count=completed_count,
        poster_paths=poster_paths
    )
    
@app.route("/library")
@login_required
def library():
    shows = UserSeries.query.filter(
        UserSeries.user_id == g.user.id,
        UserSeries.status.in_(["watching", "completed", "on_hold", "dropped"])

    ).all()

    favourite_ids = {
        favourite.tmdb_id
        for favourite in Favourite.query.filter_by(user_id=g.user.id).all()
    }

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
        favourite_ids=favourite_ids,
        total_series=total_series,
        completed_count=completed_count,
        watching_count=watching_count,
        dropped_count=dropped_count,
        on_hold_count=on_hold_count,
        genre_stats=genre_stats,
        status_genre_stats=status_genre_stats
    )

@app.route("/watchlist")
@login_required
def watchlist():
    sort = request.args.get("sort", "recent")

    query = UserSeries.query.filter_by(
        user_id=g.user.id,
        status="watchlist"
    )

    if sort == "az":
        shows = query.order_by(
            UserSeries.priority.desc(),
            UserSeries.name.asc()
        ).all()
    elif sort == "za":
        shows = query.order_by(
            UserSeries.priority.desc(),
            UserSeries.name.desc()
        ).all()
    elif sort == "rating":
        shows = query.order_by(
            UserSeries.priority.desc(),
            UserSeries.vote_average.desc()
        ).all()
    else:
        shows = query.order_by(
            UserSeries.priority.desc(),
            UserSeries.added_at.desc()
        ).all()

    priority_count = sum(1 for show in shows if show.priority)

    favourite_ids = {
        favourite.tmdb_id
        for favourite in Favourite.query.filter_by(user_id=g.user.id).all()
    }

    return render_template(
        "watchlist.html",
        shows=shows,
        user=g.user,
        priority_count=priority_count,
        favourite_ids=favourite_ids,
        sort=sort
    )
    
@app.route("/favourites")
@login_required
def favourites():
    favourite_items = (
        db.session.query(UserSeries)
        .join(Favourite, Favourite.tmdb_id == UserSeries.tmdb_id)
        .filter(
            UserSeries.user_id == g.user.id,
            Favourite.user_id == g.user.id,
            UserSeries.status.in_(TRACKED_STATUSES)
        )
        .order_by(Favourite.added_at.desc())
        .all()
    )

    ratings = [
        show.vote_average
        for show in favourite_items
        if show.vote_average is not None
    ]

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0

    return render_template(
        "favourites.html",
        user=g.user,
        favourite_items=favourite_items,
        favourite_count=len(favourite_items),
        avg_rating=avg_rating
    )

@app.route("/favourites/toggle", methods=["POST"])
@login_required
def toggle_favourite():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        return redirect(request.referrer or url_for("library"))

    tmdb_id = int(tmdb_id)

    existing_favourite = Favourite.query.filter_by(
        user_id=g.user.id,
        tmdb_id=tmdb_id
    ).first()

    if existing_favourite:
        db.session.delete(existing_favourite)
        db.session.commit()
        return redirect(request.referrer or url_for("library"))

    show = get_or_create_user_series(tmdb_id, default_status="watchlist")

    favourite = Favourite(
        user_id=g.user.id,
        tmdb_id=show.tmdb_id,
        name=show.name,
        poster_path=show.poster_path,
        vote_average=show.vote_average
    )

    db.session.add(favourite)
    db.session.commit()

    return redirect(request.referrer or url_for("library"))

@app.route("/community")
@login_required
def community():
    # Get IDs of all friends
    friend_ids = (
        db.session.query(Friendship.friend_id)
        .filter_by(user_id=g.user.id)
        .subquery()
    )

    # Get reviews + user info
    friend_reviews = (
        db.session.query(EpisodeReview, User)
        .join(User, EpisodeReview.user_id == User.id)
        .filter(EpisodeReview.user_id.in_(friend_ids))
        .order_by(EpisodeReview.created_at.desc())
        .all()
    )

    poster_paths = {}
    for review, user in friend_reviews:
        if review.series_id not in poster_paths:
            series = get_show_details(review.series_id)
            poster_paths[review.series_id] = series.get("poster_path")

    review_scores = {
        review.id: review.like_count
        for review, _ in friend_reviews
    }

    user_likes = {
        review.id: (review.liked_by.filter_by(id=g.user.id).count() > 0)
        for review, _ in friend_reviews
    }

    comment_counts = {
        review.id: review.comments.count()
        for review, _ in friend_reviews
    }

    return render_template(
        "community.html",
        user=g.user,
        friend_reviews=friend_reviews,
        poster_paths=poster_paths,
        review_scores=review_scores,
        user_likes=user_likes,
        comment_counts=comment_counts,
    )

@app.route("/reviews/like/<int:review_id>", methods=["POST"])
@login_required
def like_review(review_id):
    review = EpisodeReview.query.get_or_404(review_id)

    # FIX: ensure we have a REAL User model instance
    user = User.query.get(g.user.id)

    if review.liked_by.filter_by(id=user.id).first():
        review.liked_by.remove(user)
        user_liked = False
    else:
        review.liked_by.append(user)
        user_liked = True

    db.session.commit()

    return jsonify({
        "likes": review.like_count,
        "user_liked": user_liked
    })

@app.route("/comments/like/<int:comment_id>", methods=["POST"])
@login_required
def like_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)

    if comment.liked_by.filter_by(id=g.user.id).first():
        comment.liked_by.remove(g.user)
        db.session.commit()
        return jsonify({"likes": comment.like_count, "user_liked": False})

    comment.liked_by.append(g.user)
    db.session.commit()
    return jsonify({"likes": comment.like_count, "user_liked": True})


@app.route("/comments/add/<int:review_id>", methods=["POST"])
@login_required
def add_comment(review_id):
    review = EpisodeReview.query.get_or_404(review_id)
    text = ""
    if request.is_json:
        data = request.get_json() or {}
        text = (data.get("text") or "").strip()
    else:
        text = (request.form.get("text") or "").strip()

    if not text:
        if request.is_json:
            return jsonify({"error": "Empty comment"}), 400
        else:
            flash("Comment cannot be empty.", "error")
            return redirect(request.referrer or url_for("community"))

    comment = Comment(user_id=g.user.id, review_id=review_id, text=text)
    db.session.add(comment)
    db.session.commit()

    comments = review.comments.order_by(Comment.created_at.asc()).all()
    user_comment_likes = {c.id: (c.liked_by.filter_by(id=g.user.id).count() > 0) for c in comments}

    return render_template(
        "partials/review_comments.html",
        comments=comments,
        user_comment_likes=user_comment_likes,
        review_id=review_id,
    )

@app.route("/comments/delete/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != g.user.id:
        return jsonify({"error": "Unauthorized"}), 403

    review_id = comment.review_id
    db.session.delete(comment)
    db.session.commit()

    review = EpisodeReview.query.get_or_404(review_id)
    comments = review.comments.order_by(Comment.created_at.asc()).all()
    user_comment_likes = {c.id: (c.liked_by.filter_by(id=g.user.id).count() > 0) for c in comments}

    return render_template(
        "partials/review_comments.html",
        comments=comments,
        user_comment_likes=user_comment_likes,
        review_id=review_id,
    )

@app.route("/reviews/comments/<int:review_id>")
@login_required
def review_comments(review_id):
    review = EpisodeReview.query.get_or_404(review_id)
    comments = review.comments.order_by(Comment.created_at.asc()).all()

    user_comment_likes = {
        c.id: (c.liked_by.filter_by(id=g.user.id).count() > 0) for c in comments
    }

    return render_template(
        "partials/review_comments.html",
        comments=comments,
        user_comment_likes=user_comment_likes,
        review_id=review_id,
    )


@app.route("/friends")
@login_required
def friends():
    friendships = Friendship.query.filter_by(
        user_id=g.user.id
    ).all()

    friends = []

    for friendship in friendships:
        friend = friendship.friend
        
        if friend is None:
           db.session.delete(friendship)
           continue

        latest_review = EpisodeReview.query.filter_by(
            user_id=friend.id
        ).order_by(
            EpisodeReview.created_at.desc()
        ).first()

        watching = UserSeries.query.filter_by(
            user_id=friend.id,
            status="watching"
        ).first()

        friends.append({
            "user": friend,
            "latest_review": latest_review,
            "watching": watching
        })
    db.session.commit()
    friend_count = len(friends)

    shared_reviews_count = 0
    for item in friends:
        shared_reviews_count += EpisodeReview.query.filter_by(
            user_id=item["user"].id
        ).count()

    # Search users to add as friends
    friend_q = request.args.get("friend_q", "").strip()
    search_results = []

    if friend_q:
        current_friend_ids = [item["user"].id for item in friends]

        search_results = User.query.filter(
            User.username.ilike(f"%{friend_q}%"),
            User.id != g.user.id,
            ~User.id.in_(current_friend_ids) if current_friend_ids else True
        ).limit(10).all()

    return render_template(
        "friends.html",
        user=g.user,
        friends=friends,
        friend_count=friend_count,
        shared_reviews_count=shared_reviews_count,
        friend_q=friend_q,
        search_results=search_results
    )
    
@app.route("/friends/add/<username>", methods=["POST"])
@login_required
def add_friend(username):
    friend = User.query.filter_by(username=username).first_or_404()

    if friend.id == g.user.id:
        flash("You cannot add yourself as a friend.", "error")
        return redirect(url_for("friends"))

    existing = Friendship.query.filter_by(
        user_id=g.user.id,
        friend_id=friend.id
    ).first()

    if existing:
        flash("This user is already your friend.", "error")
        return redirect(url_for("friends"))

    friendship = Friendship(
        user_id=g.user.id,
        friend_id=friend.id
    )

    db.session.add(friendship)
    db.session.commit()

    flash(f"{friend.username} added as a friend.", "success")
    return redirect(url_for("friends"))


@app.route("/friends/remove/<username>", methods=["POST"])
@login_required
def remove_friend(username):
    friend = User.query.filter_by(username=username).first_or_404()

    friendship = Friendship.query.filter_by(
        user_id=g.user.id,
        friend_id=friend.id
    ).first_or_404()

    db.session.delete(friendship)
    db.session.commit()

    flash(f"{friend.username} removed from friends.", "success")
    return redirect(url_for("friends"))
@app.route("/stats")
@login_required
def stats():
    all_series = UserSeries.query.filter_by(user_id=g.user.id).all()

    library_series = [
        show for show in all_series
        if show.status in ["watching", "completed", "on_hold", "dropped"]
    ]

    reviews = (
        EpisodeReview.query
        .filter_by(user_id=g.user.id)
        .order_by(EpisodeReview.created_at.desc())
        .all()
    )

    favourites_count = Favourite.query.filter_by(user_id=g.user.id).count()
    friends_count = Friendship.query.filter_by(user_id=g.user.id).count()

    total_series_tracked = len(all_series)
    library_series_count = len(library_series)
    episodes_reviewed = len(reviews)
    total_reviews_written = len(reviews)

    average_rating = 0
    if reviews:
        average_rating = round(
            sum(review.rating for review in reviews if review.rating is not None) / len(reviews),
            1
        )

    status_order = ["watchlist", "watching", "completed", "on_hold", "dropped"]
    status_labels = {
        "watchlist": "Watchlist",
        "watching": "Watching",
        "completed": "Completed",
        "on_hold": "On Hold",
        "dropped": "Dropped"
    }

    status_counts = {status: 0 for status in status_order}
    for show in all_series:
        if show.status in status_counts:
            status_counts[show.status] += 1

    genre_counter = Counter()
    for show in all_series:
        if show.genres:
            for genre in show.genres.split(","):
                clean_genre = genre.strip()
                if clean_genre:
                    genre_counter[clean_genre] += 1

    top_genre = genre_counter.most_common(1)[0][0] if genre_counter else "No data yet"
    top_genres = genre_counter.most_common(6)

    filter_mode = request.args.get("range", "7d")
    start_date_str = request.args.get("start_date", "").strip()
    end_date_str = request.args.get("end_date", "").strip()

    today = datetime.utcnow().date()
    start_date = None
    end_date = today

    if filter_mode == "all":
        start_date = None
    elif filter_mode == "month":
        start_date = today.replace(day=1)
    elif filter_mode == "year":
        start_date = today.replace(month=1, day=1)
    elif filter_mode == "custom" and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = today - timedelta(days=6)
            end_date = today
            filter_mode = "7d"
    else:
        start_date = today - timedelta(days=6)
        end_date = today
        filter_mode = "7d"

    filtered_reviews = []

    for review in reviews:
        if not review.created_at:
            continue

        review_date = review.created_at.date()

        if start_date is not None:
            if start_date <= review_date <= end_date:
                filtered_reviews.append(review)
        else:
            filtered_reviews.append(review)

    filtered_reviews = sorted(
        filtered_reviews,
        key=lambda review: review.created_at,
        reverse=True
    )

    review_counts_by_day = defaultdict(int)
    rating_lists_by_day = defaultdict(list)

    for review in filtered_reviews:
        day_key = review.created_at.date()
        review_counts_by_day[day_key] += 1
        rating_lists_by_day[day_key].append(review.rating)

    review_timeline = []
    rating_timeline = []

    for day in sorted(review_counts_by_day.keys()):
        label = day.strftime("%b %d, %Y")
        review_timeline.append((label, review_counts_by_day[day]))

        ratings = rating_lists_by_day[day]
        avg_rating_for_day = round(sum(ratings) / len(ratings), 1) if ratings else 0
        rating_timeline.append((label, avg_rating_for_day))

    max_review_count = max([count for _, count in review_timeline], default=1)
    max_rating_value = max([value for _, value in rating_timeline], default=1)

    history_groups_dict = defaultdict(list)

    for review in filtered_reviews:
        day_label = review.created_at.strftime("%B %d, %Y")
        history_groups_dict[day_label].append(review)

    history_groups = []
    for day_label, day_reviews in history_groups_dict.items():
        history_groups.append({
            "date_label": day_label,
            "reviews": day_reviews
        })

    filter_label = "Recent 7 Days"
    if filter_mode == "all":
        filter_label = "All Time"
    elif filter_mode == "month":
        filter_label = "This Month"
    elif filter_mode == "year":
        filter_label = "This Year"
    elif filter_mode == "custom":
        filter_label = "Custom Range"

    return render_template(
        "stats.html",
        user=g.user,
        total_series_tracked=total_series_tracked,
        library_series_count=library_series_count,
        episodes_reviewed=episodes_reviewed,
        favourites_count=favourites_count,
        friends_count=friends_count,
        average_rating=average_rating,
        total_reviews_written=total_reviews_written,
        top_genre=top_genre,
        top_genres=top_genres,
        status_counts=status_counts,
        status_labels=status_labels,
        review_timeline=review_timeline,
        rating_timeline=rating_timeline,
        max_review_count=max_review_count,
        max_rating_value=max_rating_value,
        history_groups=history_groups,
        filter_mode=filter_mode,
        filter_label=filter_label,
        start_date_str=start_date_str,
        end_date_str=end_date_str
    )
@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=g.user)

@app.route("/settings/delete-account", methods=["POST"])
@login_required
def delete_account():
    user = User.query.get(g.user.id)

    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("settings"))

    session.clear()
    
    Friendship.query.filter(
        db.or_(
           Friendship.user_id == user.id,
           Friendship.friend_id == user.id
       )
    ).delete(synchronize_session=False)

    db.session.delete(user)
    db.session.commit()

    flash("Your account has been deleted.", "success")
    return redirect(url_for("landing"))

# -------------------- SERIES --------------------

@app.route("/series/<int:series_id>")
@login_required
def series_detail(series_id):
    url = f"{TMDB_BASE_URL}/tv/{series_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }

    response = requests.get(url, params=params)
    series = response.json()

    user_series = UserSeries.query.filter_by(
        user_id=g.user.id,
        tmdb_id=series_id
    ).first()

    is_favourite = Favourite.query.filter_by(
        user_id=g.user.id,
        tmdb_id=series_id
    ).first() is not None

    return render_template(
        "seriesdetail.html",
        series=series,
        user=g.user,
        user_series=user_series,
        is_favourite=is_favourite
    )


@app.route("/series/<int:series_id>/season/<int:season_number>")
@login_required
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

    reviews_by_episode = {}

    if g.user is not None:
        user_reviews = EpisodeReview.query.filter_by(
            user_id=g.user.id,
            series_id=series_id,
            season_number=season_number
        ).all()

        reviews_by_episode = {
            review.episode_number: review
            for review in user_reviews
        }

    return render_template(
        "seasondetail.html",
        series=series,
        season=season,
        reviews_by_episode=reviews_by_episode,
        user=g.user
    )


@app.route("/series/<int:series_id>/season/<int:season_number>/episode/<int:episode_number>/review")
@login_required
def review_episode(series_id, season_number, episode_number):
    episode_url = f"{TMDB_BASE_URL}/tv/{series_id}/season/{season_number}/episode/{episode_number}"
    series_url = f"{TMDB_BASE_URL}/tv/{series_id}"

    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }

    episode = requests.get(episode_url, params=params).json()
    series = requests.get(series_url, params=params).json()

    existing_review = EpisodeReview.query.filter_by(
        user_id=g.user.id,
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number
    ).first()

    return render_template(
        "reviewepisode.html",
        episode=episode,
        series=series,
        series_id=series_id,
        existing_review=existing_review,
        user=g.user
    )


# -------------------- WATCHLIST / LIBRARY STATUS --------------------

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
        if genre.get("name"):
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


@app.route("/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    tmdb_id = request.form.get("tmdb_id")

    if tmdb_id:
        tmdb_id = int(tmdb_id)

        Favourite.query.filter_by(
            user_id=g.user.id,
            tmdb_id=tmdb_id
        ).delete()

        UserSeries.query.filter_by(
            user_id=g.user.id,
            tmdb_id=tmdb_id,
            status="watchlist"
        ).delete()

        db.session.commit()

    return redirect(request.referrer or url_for("watchlist"))

@app.route("/watchlist/priority", methods=["POST"])
@login_required
def toggle_watchlist_priority():
    tmdb_id = request.form.get("tmdb_id")

    if not tmdb_id:
        return redirect(request.referrer or url_for("watchlist"))

    show = UserSeries.query.filter_by(
        user_id=g.user.id,
        tmdb_id=int(tmdb_id),
        status="watchlist"
    ).first()

    if show:
        show.priority = not show.priority
        db.session.commit()

    return redirect(request.referrer or url_for("watchlist"))

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

    if status == "watchlist":
        return redirect(url_for("watchlist"))

    return redirect(request.referrer or url_for("library"))


# -------------------- REVIEWS --------------------

@app.route("/reviews/add", methods=["POST"])
@login_required
def add_episode_review():
    series_id = int(request.form.get("series_id"))
    series_name = request.form.get("series_name")
    season_number = int(request.form.get("season_number"))
    episode_number = int(request.form.get("episode_number"))
    episode_name = request.form.get("episode_name")
    episode_still_path = request.form.get("episode_still_path")
    rating = float(request.form.get("rating"))
    review_text = request.form.get("review_text", "").strip()

    if not review_text:
        flash("Please write a review before saving.", "error")
        return redirect(request.referrer or url_for("profile"))

    existing_review = EpisodeReview.query.filter_by(
        user_id=g.user.id,
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number
    ).first()

    if existing_review:
        existing_review.series_name = series_name
        existing_review.episode_name = episode_name
        existing_review.episode_still_path = episode_still_path
        existing_review.rating = rating
        existing_review.review_text = review_text
    else:
        review = EpisodeReview(
            user_id=g.user.id,
            series_id=series_id,
            series_name=series_name,
            season_number=season_number,
            episode_number=episode_number,
            episode_name=episode_name,
            episode_still_path=episode_still_path,
            rating=rating,
            review_text=review_text
        )
        db.session.add(review)

    db.session.commit()
    flash("Review saved.", "success")

    return redirect(
        url_for(
            "review_episode",
            series_id=series_id,
            season_number=season_number,
            episode_number=episode_number
        )
    )


@app.route("/reviews/<int:review_id>/delete", methods=["POST"])
@login_required
def delete_episode_review(review_id):
    review = EpisodeReview.query.filter_by(
        id=review_id,
        user_id=g.user.id
    ).first_or_404()

    series_id = review.series_id
    season_number = review.season_number

    db.session.delete(review)
    db.session.commit()

    flash("Review deleted.", "success")

    return redirect(request.referrer or url_for(
        "season_detail",
        series_id=series_id,
        season_number=season_number
    ))


if __name__ == "__main__":
    app.run(debug=True)