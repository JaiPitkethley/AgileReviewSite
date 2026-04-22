# AgileReviewSite

UWA Agile Web Development project for 2026.

## Project Overview

This project is currently a Flask-based local web application prototype for a series tracking and review platform.

The current version includes:
- landing page
- login page
- signup page
- dashboard page
- local backend authentication flow
- local SQLite database storage

Users can create an account, sign in, stay logged in with session support, access the dashboard, and log out.

---

## Current Features

### Frontend / Page Flow
- Landing page
- Login page
- Signup page
- Dashboard page
- Navigation between all main pages

### Backend / Authentication
- Flask backend
- Local SQLite database
- User signup
- User login
- Password hashing
- Session-based login
- Logout
- Dashboard connected to the currently logged-in user

### Current Page Flow
- `landing -> login`
- `landing -> signup`
- `login -> dashboard`
- `signup -> dashboard`
- `dashboard -> logout -> landing`

---

## Project Structure

```text
AgileReviewSite/
├── app.py
├── README.md
├── requirements.txt
├── .gitignore
├── templates/
│   ├── landing.html
│   ├── login.html
│   ├── signup.html
│   └── reviewsitehome.html
└── static/
    └── styles.css
````

---

## How to Run the App Locally

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd AgileReviewSite
```

### 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 3. Run the Flask app

```bash
python3 app.py
```

### 4. Open in browser

```text
http://127.0.0.1:5000
```

---

## Main Routes

* Landing page: `http://127.0.0.1:5000/landing`
* Login page: `http://127.0.0.1:5000/login`
* Signup page: `http://127.0.0.1:5000/signup`
* Dashboard: `http://127.0.0.1:5000/dashboard`
* Logout: `http://127.0.0.1:5000/logout`

---

## Test Accounts

If you are using the same local database file, these test accounts may work:

* `test1@example.com` / `123456`
* `test2@example.com` / `123456`

If these accounts do not work on your machine, just create a new account locally using the signup page.

---

## Local Database Notes

This project currently uses a **local SQLite database** (`users.db`).

That means:

* the database is generated locally when running the app
* account data is stored only on the local machine running the app
* if another person clones the project, they will not automatically share the same registered accounts unless the same database file is also shared

So the current backend/database setup works locally, but it is **not yet a shared cloud-hosted database system**.

---

## Current Limitations

* database is local only
* no cloud deployment yet
* no shared hosted database yet
* dashboard content is mostly static except for logged-in user integration
* account data is not synchronized across different cloned copies of the project

---

## Notes for Developers

* Password hashing is enabled in the backend
* Session-based authentication is enabled
* The dashboard uses the logged-in user data for display
* Local-only files such as `users.db` and `.DS_Store` should not be committed to the repository

---

## Future Improvements

Possible next steps:

* deploy the Flask app online
* move from local SQLite to a shared database such as PostgreSQL
* connect dashboard features to real user data
* implement watchlist, favourites, reviews, and friend features
* improve dashboard integration across all branches

---

## Tech Stack

* Python
* Flask
* SQLite
* HTML
* CSS
* JavaScript
