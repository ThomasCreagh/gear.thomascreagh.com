from routers import users, items, loans, admin
import models
from database import engine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from config import read_secret
import os

load_dotenv()

UPLOAD_DIR = read_secret("UPLOAD_DIR", "uploads")

models.Base.metadata.create_all(bind=engine)

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


# Static mounts last — catch-all, would swallow API routes if mounted first
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
