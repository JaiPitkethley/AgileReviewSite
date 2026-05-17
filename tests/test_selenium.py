"""
test_selenium.py — Browser-driven tests for AgileReviewSite.

These tests launch a real Chrome browser against a running Flask server and
verify the application's UI and end-to-end flows.

Setup (run once)
----------------
    pip install selenium pytest webdriver-manager

    # Optionally start the server manually in a separate terminal:
    python app.py   # listens on http://127.0.0.1:5000

Run
---
    pytest tests/test_selenium.py -v

    # Single class:
    pytest tests/test_selenium.py::TestAuthFlow -v

    # Headless (recommended for CI / marking):
    HEADLESS=1 pytest tests/test_selenium.py -v

Notes
-----
- If no server is already running on port 5000, the module starts one
  automatically in a background daemon thread using an in-memory SQLite DB.
- Each test class uses unique, randomly-generated usernames and emails so
  tests do not interfere with each other.
- Set the HEADLESS environment variable to "1" to suppress the browser window.

Python 3.12 compatibility
-------------------------
- assertEquals() (removed in 3.12) is replaced throughout with assertEqual().
- WTF_CSRF_ENABLED=False and WTF_CSRF_CHECK_DEFAULT=False are both required so
  Flask-WTF's CSRFProtect extension does not reject form POSTs from the browser.
"""

import os
import sys
import time
import uuid
import socket
import threading
import unittest

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import TimeoutException

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL  = "http://127.0.0.1:5000"
HEADLESS  = os.environ.get("HEADLESS", "0") == "1"
WAIT_SECS = 8

# A well-known TMDB series used for series/season/episode page tests.
# Breaking Bad (id=1396) is unlikely to be removed from TMDB.
TEST_TMDB_ID = 1396


# ---------------------------------------------------------------------------
# Automatic Flask server startup
# ---------------------------------------------------------------------------

def _is_server_running(host="127.0.0.1", port=5000, timeout=1.0):
    """Return True if something is already accepting connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _start_flask_server():
    """
    Start the Flask dev server in a background daemon thread backed by an
    in-memory SQLite database.  No-op if the server is already running.
    """
    if _is_server_running():
        return

    tests_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir   = os.path.dirname(tests_dir)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    os.environ.setdefault("SECRET_KEY",      "selenium-test-secret-key")
    os.environ.setdefault("TMDB_API_KEY",    "test_api_key")
    os.environ.setdefault("TMDB_READ_TOKEN", "test_read_token")

    from app import app, db

    app.config.update(
        TESTING=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        WTF_CSRF_CHECK_DEFAULT=False,
        SECRET_KEY="selenium-test-secret-key",
    )

    with app.app_context():
        db.create_all()

    def _run():
        app.run(host="127.0.0.1", port=5000, debug=False,
                use_reloader=False, threaded=True)

    threading.Thread(target=_run, daemon=True).start()

    deadline = time.time() + 10
    while time.time() < deadline:
        if _is_server_running():
            return
        time.sleep(0.1)

    raise RuntimeError("Flask server did not start within 10 seconds.")


# Start the server as soon as this module is imported (before any test runs).
_start_flask_server()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique(prefix="user"):
    """Generate a short unique string — used for usernames and email prefixes."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def make_driver():
    """Build a Chrome WebDriver, headless if HEADLESS=1."""
    opts = ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=opts
        )
    except ImportError:
        return webdriver.Chrome(options=opts)


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------

class BaseSeleniumTest(unittest.TestCase):
    """
    Shared setup, teardown, and navigation helpers for all Selenium test classes.

    A single Chrome instance is created per test class (setUpClass) and reused
    across all tests within that class.  Cookies are cleared between tests to
    simulate a fresh browser session.
    """

    @classmethod
    def setUpClass(cls):
        cls.driver = make_driver()
        cls.driver.implicitly_wait(3)
        cls.wait = WebDriverWait(cls.driver, WAIT_SECS)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def setUp(self):
        self.driver.delete_all_cookies()

    # -- navigation ----------------------------------------------------------

    def go(self, path="/"):
        self.driver.get(BASE_URL + path)

    def url_contains(self, fragment, timeout=WAIT_SECS):
        try:
            WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))
            return True
        except TimeoutException:
            return False

    def wait_for_text(self, text, timeout=WAIT_SECS):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: text in d.page_source
            )
            return True
        except TimeoutException:
            return False

    # -- element helpers -----------------------------------------------------

    def find(self, by, value):
        return self.wait.until(EC.presence_of_element_located((by, value)))

    def click(self, by, value):
        el = self.wait.until(EC.element_to_be_clickable((by, value)))
        el.click()
        return el

    def fill(self, by, value, text):
        el = self.find(by, value)
        el.clear()
        el.send_keys(text)
        return el

    # -- auth helpers --------------------------------------------------------

    def signup(self, username, email, password):
        self.go("/signup")
        self.fill(By.NAME, "username", username)
        self.fill(By.NAME, "email",    email)
        self.fill(By.NAME, "password", password)
        self.find(By.CSS_SELECTOR, "button[type='submit']").click()

    def login(self, email, password):
        self.go("/login")
        self.fill(By.NAME, "email",    email)
        self.fill(By.NAME, "password", password)
        self.find(By.CSS_SELECTOR, "button[type='submit']").click()

    def signup_and_login(self, username=None, email=None, password="password123"):
        """Sign up a fresh account; returns (username, email, password)."""
        username = username or unique("user")
        email    = email    or f"{unique('mail')}@example.com"
        self.signup(username, email, password)
        self.url_contains("/dashboard")
        return username, email, password


# ===========================================================================
# 1.  AUTH FLOW
# ===========================================================================

class TestAuthFlow(BaseSeleniumTest):

    def test_01_landing_page_loads(self):
        self.go("/")
        self.assertTrue(self.url_contains("/landing"))
        self.assertIn("SERIES TRACKER", self.driver.page_source.upper())

    def test_03_signup_redirects_to_dashboard(self):
        username = unique("signup")
        self.signup(username, f"{username}@example.com", "password123")
        self.assertTrue(
            self.url_contains("/dashboard"),
            "Expected redirect to /dashboard after successful signup",
        )

    def test_04_signup_rejects_duplicate_email(self):
        username = unique("dup")
        email    = f"{username}@example.com"
        self.signup(username, email, "password123")
        self.url_contains("/dashboard")
        self.go("/logout")
        self.signup(unique("dup2"), email, "password123")
        self.assertTrue(
            self.wait_for_text("already registered"),
            "Expected 'already registered' error on duplicate email",
        )

    def test_09_logout_redirects_to_landing(self):
        self.signup_and_login()
        self.go("/logout")
        self.assertTrue(self.url_contains("/landing"))

    def test_10_unauthenticated_access_to_dashboard_redirects_to_login(self):
        self.go("/logout")
        self.go("/dashboard")
        self.assertTrue(
            self.url_contains("/login"),
            "Unauthenticated /dashboard should redirect to /login",
        )

    def test_11_topbar_shows_username_when_logged_in(self):
        username, _, _ = self.signup_and_login()
        self.go("/dashboard")
        self.assertIn(username, self.driver.page_source)

    def test_12_password_field_toggle_reveals_text(self):
        self.go("/login")
        pw_field = self.find(By.ID, "login-password")
        toggle   = self.find(By.CSS_SELECTOR, ".password-toggle")
        self.assertEqual(pw_field.get_attribute("type"), "password")
        toggle.click()
        self.assertEqual(pw_field.get_attribute("type"), "text")


# ===========================================================================
# 2.  NAVIGATION
# ===========================================================================

class TestNavigation(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def _click_sidebar_link(self, label):
        """Click the first sidebar nav item whose text contains label."""
        for link in self.driver.find_elements(By.CSS_SELECTOR, ".sb-item"):
            if label.lower() in link.text.lower():
                link.click()
                return
        self.fail(f"Sidebar link '{label}' not found")

    def test_nav_to_watchlist(self):
        self._click_sidebar_link("Watchlist")
        self.assertTrue(self.url_contains("/watchlist"))

    def test_nav_to_library(self):
        self._click_sidebar_link("Library")
        self.assertTrue(self.url_contains("/library"))

    def test_nav_to_favourites(self):
        self._click_sidebar_link("Favourites")
        self.assertTrue(self.url_contains("/favourites"))

    def test_nav_to_community(self):
        self._click_sidebar_link("Community")
        self.assertTrue(self.url_contains("/community"))

    def test_nav_to_friends(self):
        self._click_sidebar_link("Friends")
        self.assertTrue(self.url_contains("/friends"))

    def test_nav_to_profile(self):
        self._click_sidebar_link("Profile")
        self.assertTrue(self.url_contains("/profile"))

    def test_nav_to_stats(self):
        self._click_sidebar_link("Stats")
        self.assertTrue(self.url_contains("/stats"))

    def test_nav_to_settings(self):
        self._click_sidebar_link("Settings")
        self.assertTrue(self.url_contains("/settings"))

    def test_nav_logout_from_sidebar(self):
        self._click_sidebar_link("Logout")
        self.assertTrue(self.url_contains("/landing"))

    def test_topbar_search_input_present(self):
        self.go("/dashboard")
        self.assertTrue(self.find(By.ID, "topbarSearchInput").is_displayed())

    def test_topbar_search_submits_query(self):
        self.go("/dashboard")
        search = self.find(By.ID, "topbarSearchInput")
        search.send_keys("Breaking Bad")
        search.send_keys(Keys.RETURN)
        self.assertTrue(self.url_contains("/dashboard"))


# ===========================================================================
# 3.  WATCHLIST
# ===========================================================================

class TestWatchlist(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_watchlist_page_loads(self):
        self.go("/watchlist")
        self.assertEqual(self.driver.current_url, BASE_URL + "/watchlist")

    def test_watchlist_empty_state_shows_message(self):
        self.go("/watchlist")
        self.assertIn("empty", self.driver.page_source.lower())

    def test_watchlist_page_shows_priority_label(self):
        self.go("/watchlist")
        self.assertIn("Priority", self.driver.page_source)

    def test_watchlist_page_shows_saved_label(self):
        self.go("/watchlist")
        self.assertIn("Saved", self.driver.page_source)

class TestLibrary(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_library_page_loads(self):
        self.go("/library")
        self.assertEqual(self.driver.current_url, BASE_URL + "/library")

    def test_library_page_no_server_error(self):
        self.go("/library")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_library_page_shows_heading(self):
        self.go("/library")
        self.assertIn("Library", self.driver.page_source)


# ===========================================================================
# 5.  FAVOURITES
# ===========================================================================

class TestFavourites(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_favourites_page_loads(self):
        self.go("/favourites")
        self.assertEqual(self.driver.current_url, BASE_URL + "/favourites")

    def test_favourites_page_no_server_error(self):
        self.go("/favourites")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_favourites_page_shows_heading(self):
        self.go("/favourites")
        self.assertIn("Favourite", self.driver.page_source)


# ===========================================================================
# 6.  COMMUNITY
# ===========================================================================

class TestCommunity(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_community_page_loads(self):
        self.go("/community")
        self.assertEqual(self.driver.current_url, BASE_URL + "/community")

    def test_community_page_no_server_error(self):
        self.go("/community")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_community_page_shows_heading(self):
        self.go("/community")
        self.assertIn("Community", self.driver.page_source)


# ===========================================================================
# 8.  STATS
# ===========================================================================

class TestStats(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_stats_page_loads(self):
        self.go("/stats")
        self.assertEqual(self.driver.current_url, BASE_URL + "/stats")

    def test_stats_page_no_server_error(self):
        self.go("/stats")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_all_time_filter(self):
        self.go("/stats?range=all")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_month_filter(self):
        self.go("/stats?range=month")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_year_filter(self):
        self.go("/stats?range=year")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_custom_filter_valid_dates(self):
        self.go("/stats?range=custom&start_date=2026-01-01&end_date=2026-12-31")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_custom_filter_invalid_dates_no_crash(self):
        self.go("/stats?range=custom&start_date=notadate&end_date=alsowrong")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_stats_page_shows_filter_labels(self):
        self.go("/stats")
        source    = self.driver.page_source
        has_label = any(
            label in source
            for label in ["Recent 7 Days", "All Time", "This Month", "This Year"]
        )
        self.assertTrue(has_label, "Expected a time-range filter label on the stats page")


# ===========================================================================
# 9.  SETTINGS & ACCOUNT DELETION
# ===========================================================================

class TestSettings(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.uname, self.email, self.pwd = self.signup_and_login()

    def test_settings_page_loads(self):
        self.go("/settings")
        self.assertEqual(self.driver.current_url, BASE_URL + "/settings")

    def test_settings_shows_danger_zone(self):
        self.go("/settings")
        self.assertIn("Danger Zone", self.driver.page_source)

    def test_settings_shows_delete_account_button(self):
        self.go("/settings")
        self.assertIn("Delete Account", self.driver.page_source)

    def test_dismissing_confirm_dialog_keeps_account(self):
        """Dismissing the JS confirm() dialog should leave the account intact."""
        self.go("/settings")
        self.driver.execute_script("window.confirm = function() { return false; }")
        self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".danger-zone button[type='submit']")
            )
        ).click()
        time.sleep(0.5)
        self.assertIn("/settings", self.driver.current_url)

class TestProfile(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.uname, self.email, self.pwd = self.signup_and_login()

    def test_profile_page_loads(self):
        self.go("/profile")
        self.assertEqual(self.driver.current_url, BASE_URL + "/profile")

    def test_profile_shows_username(self):
        self.go("/profile")
        self.assertIn(self.uname, self.driver.page_source)

    def test_profile_shows_review_section(self):
        self.go("/profile")
        self.assertIn("review", self.driver.page_source.lower())

    def test_own_public_profile_accessible(self):
        self.go(f"/profile/{self.uname}")
        self.assertEqual(
            self.driver.current_url, BASE_URL + f"/profile/{self.uname}"
        )
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_nonexistent_profile_returns_404(self):
        self.go("/profile/this_user_does_not_exist_xyz999")
        source = self.driver.page_source
        self.assertTrue(
            "404" in source or "Not Found" in source or "404" in self.driver.title,
            "Expected a 404 response for a nonexistent user profile",
        )


# ===========================================================================
# 11.  SERIES & REVIEW PAGES
# ===========================================================================

class TestSeriesAndReviews(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_season_detail_page_loads(self):
        self.go(f"/series/{TEST_TMDB_ID}/season/1")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

class TestUIDetails(BaseSeleniumTest):

    def setUp(self):
        super().setUp()
        self.signup_and_login()

    def test_sidebar_visible_on_dashboard(self):
        self.go("/dashboard")
        sidebar = self.find(By.CSS_SELECTOR, ".sidebar")
        self.assertIsNotNone(sidebar, "Expected .sidebar element to be present in the DOM")

    def test_topbar_visible_on_dashboard(self):
        self.go("/dashboard")
        self.assertTrue(self.find(By.CSS_SELECTOR, ".topbar").is_displayed())

    def test_theme_toggle_button_present(self):
        self.go("/dashboard")
        self.assertTrue(self.find(By.CSS_SELECTOR, ".theme-toggle").is_displayed())

    def test_theme_toggle_changes_body_class(self):
        self.go("/dashboard")
        toggle = self.find(By.CSS_SELECTOR, ".theme-toggle")
        body   = self.driver.find_element(By.TAG_NAME, "body")
        before = body.get_attribute("class")
        toggle.click()
        time.sleep(0.3)
        after = body.get_attribute("class")
        self.assertNotEqual(before, after, "Body class should change after clicking theme toggle")

    def test_sidebar_toggle_button_present(self):
        self.go("/dashboard")
        self.assertTrue(self.find(By.ID, "sidebarToggle").is_displayed())

    def test_page_title_on_watchlist(self):
        self.go("/watchlist")
        self.assertIn("Watchlist", self.driver.title)

    def test_page_title_on_friends(self):
        self.go("/friends")
        self.assertIn("Friends", self.driver.title)

    def test_page_title_on_library(self):
        self.go("/library")
        self.assertIn("Library", self.driver.title)

    def test_landing_page_accessible_after_logout(self):
        self.go("/logout")
        self.url_contains("/landing")
        self.assertNotIn("Internal Server Error", self.driver.page_source)

    def test_dashboard_loads_at_mobile_width(self):
        """The page should render without errors at a narrow viewport."""
        self.driver.set_window_size(375, 812)
        self.go("/dashboard")
        self.assertNotIn("Internal Server Error", self.driver.page_source)
        self.driver.set_window_size(1280, 900)


if __name__ == "__main__":
    unittest.main(verbosity=2)
