from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func
from app import db
from app.models import User, EpisodeReview, Comment

main = Blueprint("main", __name__)


@main.before_request
def before_request():
    """Load user into g object for all requests."""
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = db.session.get(User, user_id)


@main.route("/", endpoint="index")
def index():
    return redirect(url_for("main.landing"))


@main.route("/landing", endpoint="landing")
def landing():
    return render_template("landing.html", user=g.user)


@main.route("/signup", methods=["GET", "POST"], endpoint="signup")
def signup():
    """Handle user signup."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        # Validate inputs
        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("main.signup"))

        # Check if user already exists
        if db.session.query(User).filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("main.signup"))

        if db.session.query(User).filter_by(username=username).first():
            flash("Username already taken.", "error")
            return redirect(url_for("main.signup"))

        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        flash("Account created successfully!", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("signup.html", user=g.user)


@main.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    """Handle user login."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = db.session.query(User).filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            flash("Logged in successfully!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for("main.login"))

    return render_template("login.html", user=g.user)


@main.route("/logout", endpoint="logout")
def logout():
    """Handle user logout."""
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("main.landing"))


@main.route("/dashboard", endpoint="dashboard")
def dashboard():
    """User dashboard page."""
    if not g.user:
        return redirect(url_for("main.login"))
    
    return render_template("reviewsitehome.html", user=g.user)


@main.route("/stats", endpoint="stats")
def stats():
    """User statistics page."""
    if not g.user:
        return redirect(url_for("main.login"))
    
    # Get user stats
    total_reviews = db.session.query(func.count(EpisodeReview.id)).filter_by(user_id=g.user.id).scalar()
    avg_rating = 0
    reviews = db.session.query(EpisodeReview).filter_by(user_id=g.user.id).all()
    if reviews:
        avg_rating = sum(r.rating for r in reviews) / len(reviews)

    return render_template(
        "stats.html",
        user=g.user,
        total_reviews=total_reviews,
        avg_rating=round(avg_rating, 1),
    )


# Stub routes for templates that reference these
@main.route("/library", endpoint="library")
def library():
    """User library page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("library.html", user=g.user)


@main.route("/profile", endpoint="profile")
def profile():
    """User profile page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("profile.html", user=g.user)


@main.route("/watchlist", endpoint="watchlist")
def watchlist():
    """User watchlist page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("watchlist.html", user=g.user)


@main.route("/favourites", endpoint="favourites")
def favourites():
    """User favourites page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("favourites.html", user=g.user)


@main.route("/settings", endpoint="settings")
def settings():
    """User settings page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("settings.html", user=g.user)


@main.route("/community", endpoint="community")
def community():
    """Community page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("community.html", user=g.user)


@main.route("/friends", endpoint="friends")
def friends():
    """Friends page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("friends.html", user=g.user)


@main.route("/user/<username>", endpoint="public_profile")
def public_profile(username):
    """Public profile page."""
    profile_user = db.session.query(User).filter_by(username=username).first()
    if not profile_user:
        flash("User not found.", "error")
        return redirect(url_for("main.community"))
    return render_template("friendprofile.html", user=g.user, profile_user=profile_user)


@main.route("/season/<int:series_id>/<int:season>", endpoint="season_detail")
def season_detail(series_id, season):
    """Season detail page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("seasondetail.html", user=g.user, series_id=series_id, season=season)


@main.route("/series/<int:series_id>", endpoint="series_detail")
def series_detail(series_id):
    """Series detail page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("seriesdetail.html", user=g.user, series_id=series_id)


@main.route("/review-episode/<int:series_id>/<int:season>/<int:episode>", endpoint="review_episode")
def review_episode(series_id, season, episode):
    """Review episode page."""
    if not g.user:
        return redirect(url_for("main.login"))
    return render_template("reviewepisode.html", user=g.user, series_id=series_id, season=season, episode=episode)


# Stub POST endpoints
@main.route("/add-friend/<username>", methods=["POST"], endpoint="add_friend")
def add_friend(username):
    """Add a friend."""
    if not g.user:
        return redirect(url_for("main.login"))
    flash(f"Added {username} as a friend!", "success")
    return redirect(request.referrer or url_for("main.friends"))


@main.route("/remove-friend/<username>", methods=["POST"], endpoint="remove_friend")
def remove_friend(username):
    """Remove a friend."""
    if not g.user:
        return redirect(url_for("main.login"))
    flash(f"Removed {username} from friends.", "success")
    return redirect(request.referrer or url_for("main.friends"))


@main.route("/toggle-favourite", methods=["POST"], endpoint="toggle_favourite")
def toggle_favourite():
    """Toggle favourite."""
    if not g.user:
        return redirect(url_for("main.login"))
    flash("Favourite toggled.", "success")
    return redirect(request.referrer or url_for("main.library"))
