from routers import users, items, loans, admin
import models
from database import engine, SessionLocal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from config import read_secret
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text
import os
import logging

load_dotenv()

logger = logging.getLogger("uvicorn.error")

UPLOAD_DIR = read_secret("UPLOAD_DIR", "uploads")

models.Base.metadata.create_all(bind=engine)

# ``create_all`` does not alter tables that already exist. Keep additive,
# backwards-compatible fields in sync for installations that upgrade without
# running the optional SQL migration script first.
with engine.begin() as connection:
    connection.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS image_path VARCHAR"))
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
    connection.execute(text("ALTER TABLE loans ADD COLUMN IF NOT EXISTS door_code VARCHAR"))
    connection.execute(text("ALTER TABLE loans ADD COLUMN IF NOT EXISTS locker_codes JSONB"))
    connection.execute(text("ALTER TABLE loans ADD COLUMN IF NOT EXISTS start_date TIMESTAMP"))
    connection.execute(text("ALTER TABLE gear_groups ADD COLUMN IF NOT EXISTS group_ids JSONB NOT NULL DEFAULT '[]'::jsonb"))
    # Loans created before the trust-based flow used this intermediate state.
    # They no longer need a locker verification step.
    connection.execute(text("UPDATE loans SET status = 'active' WHERE status = 'pending_verification'"))

app = FastAPI(title="Gear Renting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers first — must be before any catch-all static mounts
app.include_router(users.router)
app.include_router(items.router)
app.include_router(loans.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# In-app scheduler: auto-close T-wall loans older than 24h.
# Runs inside the FastAPI process, no external cron needed.
# ---------------------------------------------------------------------------
scheduler = BackgroundScheduler()


def scheduled_twall_autoclose():
    db = SessionLocal()
    try:
        closed = loans.run_twall_autoclose(db)
        if closed:
            logger.info(f"[scheduler] Auto-closed twall loans: {closed}")
    except Exception:
        logger.exception("[scheduler] twall autoclose job failed")
    finally:
        db.close()


@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(scheduled_twall_autoclose, "interval", minutes=15)
    scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown(wait=False)


# Static mounts last — catch-all, would swallow API routes if mounted first
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
