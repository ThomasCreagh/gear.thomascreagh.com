# Gear Renting Website

A web-based gear borrowing and return system for [gear.thomascreagh.com](http://gear.thomascreagh.com). Users can browse available gear, request to borrow items, and return them via a physical locker system. Tom (admin) manages user accounts, approves access, and manages the gear catalogue.

---

## Features

- User login with JWT authentication
- Browse and request available gear
- Photo confirmation required on borrow and return
- Automatic audit logging of all actions
- Admin dashboard for Tom (approve requests, manage users, and manage gear)
- Email notifications via self-hosted mail server (gear@thomascreagh.com)
- Password reset handled in person with Tom

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Auth | JWT (python-jose) |
| Email | smtplib (self-hosted SMTP) |
| Frontend | HTML, CSS, Vanilla JS |

---

## Project Structure

```
gear-renting/
├── backend/
│   ├── main.py              # App entry point, CORS config
│   ├── models.py            # SQLAlchemy table definitions
│   ├── schemas.py           # Pydantic request/response models
│   ├── database.py          # DB session setup
│   ├── auth.py              # JWT creation, password hashing
│   ├── email.py             # smtplib mailer
│   ├── .env                 # Secrets, SMTP credentials (never commit)
│   ├── requirements.txt
│   └── routers/
│       ├── users.py         # Register, login
│       ├── items.py         # Gear CRUD
│       ├── loans.py         # Borrow, return
│       └── admin.py         # Tom's admin actions
│
└── frontend/
    ├── index.html           # Login page
    ├── gear.html            # Browse & borrow gear
    ├── return.html          # Return gear
    ├── admin.html           # Tom's dashboard
    └── static/
        ├── style.css
        └── api.js           # Fetch wrapper + JWT header injection
```

---

## Database Tables

- `users` — id, email, password_hash, is_admin, is_approved
- `items` — id, name, description, available
- `loans` — id, user_id, item_ids, booking dates, due_date, status, created_at
- `audit_log` — id, user_id, action, timestamp

---

## User Flows

### Borrowing gear
1. User logs in at gear.thomascreagh.com
2. If not in approved list → can request access from Tom
3. Tom approves → user can browse available gear
4. User selects items and number of days (max N days)
5. System logs the request and notifies Tom if required
6. User takes the gear from the physical locker and logs each item
7. All item availability updates in real time

### Returning gear
1. User logs in and selects items they are returning
2. System checks all items are accounted for — flags discrepancies immediately
3. User takes a photo of each locker after returning the gear
4. System logs exact timestamp and who returned what

### Account creation
1. User goes to Tom in person with TCD card and email address
2. Tom verifies and creates account
3. Credentials sent to user via gear@thomascreagh.com

### Password reset
- User requests reset in person with Tom
- Tom handles password resets in person after confirming the member's identity

### What Tom does weekly
- Updates public code on the locker

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/login` | Login, returns JWT |
| GET | `/items` | List available gear |
| POST | `/loans` | Request to borrow items |
| POST | `/loans/{id}/return` | Return items |
| GET | `/admin/users` | List all users (admin) |
| POST | `/admin/users/{id}/approve` | Approve user access (admin) |
| GET | `/admin/loans` | View all active loans (admin) |

---

## Setup

### Requirements

- Python 3.11+
- PostgreSQL
- Self-hosted SMTP mail server

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your values
uvicorn main:app --reload
```

### Environment variables (`.env`)

```
DATABASE_URL=postgresql://user:password@localhost/gear
SECRET_KEY=your-jwt-secret
SMTP_HOST=your-mail-server.com
SMTP_PORT=587
SMTP_USER=gear@thomascreagh.com
SMTP_PASS=your-password
```

### Frontend

No build step needed. Open any `.html` file directly or serve with:

```bash
cd frontend
python3 -m http.server 8080
```

Update the `API_BASE` variable in `static/api.js` to point to your backend URL.

---

## Dependencies

```
fastapi
uvicorn
sqlalchemy
psycopg2-binary
python-jose[cryptography]
passlib[bcrypt]
pydantic[email]
python-dotenv
```

---

## Security Notes

- Never commit `.env` to version control — add it to `.gitignore`
- Rotate `SECRET_KEY` if compromised (invalidates all sessions)
- Users who fail to return items on time are locked out until resolved

## Performance and verification

The server still installs dependencies with `pip install -r backend/requirements.txt`.
No frontend build step, Node runtime, or uv installation is required to serve the app.

Loan actions now update the page from the saved loan returned by the API instead
of refetching loans, items, and groups after every action. Opening My Loans starts
its independent requests together. Item availability on the page is updated for
the affected loan; the backend still validates availability before accepting gear.
Changes made by other users are fetched on page reload, rather than through live
inventory subscriptions. Existing photo/return response fields are preserved, and
the frontend falls back to refetching when talking to an older backend.

Backend query changes:

- My Loans fetches photos in batches instead of separately for every loan.
- The admin loan list joins borrowers and batches photos and item lookups.
- Item edits fetch changed items together; returns and automatic closures update
  availability in batches. Additions lock item rows on PostgreSQL while validating.
- Locker code lookup selects the latest codes together, including the door code.
- Nested gear groups and overdue reminders batch their related record lookups.
- Catalogue responses use gzip when the client supports it. Uploaded photos and
  responses containing locker codes or credentials are not compressed by the app.

With a local fixture of 12 loans, list queries (excluding authentication) fell from
13 to 2 for My Loans and from 16 to 3 for the admin list. Returning 20 items uses
one item UPDATE. These are query-count checks, not production latency benchmarks;
SQLAlchemy may split very large photo batches into multiple queries.

Responses include `Server-Timing: app;dur=...` in milliseconds. Compare this header
in the browser's Network panel with the overall request duration after restarting
the backend. It measures time inside the application up to response headers,
including request parsing and database work; it excludes subsequent response
transfer and time spent outside the app, such as proxy queues and network travel.

To run regression checks in a Python environment with the requirements installed:

```bash
python -m unittest discover -s backend/tests -v
```

Tests use an isolated SQLite database and temporary uploads, with no real email
delivery. PostgreSQL locking behaviour and live server latency need deployment
verification. Optional frontend request/state checks use Node's built-in runner:

```bash
node --test frontend/tests/loans.test.cjs
```

Account creation, password resets, and overdue reminders still send email before
responding. Those actions can be delayed by SMTP; moving them to a durable job queue
would be a separate change to email delivery behaviour. Loan actions do not send
email. Database indexes and hosting/network latency should be investigated against
the deployed database if server timings remain high.
