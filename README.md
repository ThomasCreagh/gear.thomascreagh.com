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
