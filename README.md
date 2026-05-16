# AgileReviewSite — Test Suite

## Structure

```
tests/
├── conftest.py       # Shared fixtures (in-memory DB, test client, auth helper)
├── test_unit.py      # 50 unit tests (no browser required)
└── test_selenium.py  # Selenium browser tests (Chrome headless required)
```

## Setup

```bash
# Install dependencies (if not already installed)
pip install -r requirements.txt
pip install pytest selenium webdriver-manager
```

## Running Tests

### Unit tests only (fast, no browser needed)
```bash
cd AgileReviewSite
pytest tests/test_unit.py -v
```

### Selenium tests (requires Chrome + ChromeDriver)
```bash
pytest tests/test_selenium.py -v
```

### Full suite
```bash
pytest tests/ -v
```

---

## What's covered

### Unit Tests (`test_unit.py`) — 50 tests

| Class | What's tested |
|---|---|
| `TestHelpers` | `get_first_genre`, `get_genre_stats` helper functions |
| `TestUserAccounts` | Signup, duplicate detection, login, logout, delete account |
| `TestAuthGuard` | `@login_required` on all 8 protected routes |
| `TestWatchlist` | Page load, remove, priority toggle on/off |
| `TestLibrary` | Page load, status updates (watching/completed), invalid status rejected |
| `TestFavourites` | Page load, toggle add, toggle remove |
| `TestEpisodeReviews` | Add review, empty text rejected, update existing, delete, field storage |
| `TestFriends` | Add, self-add blocked, duplicate blocked, remove, friend profile access, non-friend blocked |
| `TestDatabaseConstraints` | Unique constraints, password hashing, cascade deletes |

### Selenium Tests (`test_selenium.py`)

| Class | What's tested |
|---|---|
| `TestLandingPage` | Page loads, signup/login links present |
| `TestSignupFlow` | Form fields present, successful redirect, duplicate email error |
| `TestLoginFlow` | Form fields, valid login redirect, invalid login error |
| `TestNavigation` | All 8 main pages load when authenticated, redirect when logged out, navbar present |
| `TestLogout` | Redirects to landing, subsequent protected page access blocked |
| `TestResponsive` | Mobile viewport (375px) no horizontal scroll, desktop renders, CSS loaded |
| `TestFriendsPage` | Search form present, results displayed |

---

## Design Notes

- **Isolated database**: unit tests use SQLite in-memory (`sqlite:///:memory:`), so the production `users.db` is never touched.
- **CSRF disabled**: `WTF_CSRF_ENABLED=False` in test config lets form POSTs work without tokens.
- **TMDB API**: review tests that redirect to the episode page don't follow redirects, since that page calls the live TMDB API. The DB write is tested directly instead.
- **Selenium server**: a live Flask server is spun up on a random free port in a background thread for the duration of the Selenium module.
