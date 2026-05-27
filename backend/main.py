from routers import users, items, loans, admin
import models
from database import engine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

load_dotenv()


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gear Renting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads directory
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(users.router)
app.include_router(items.router)
app.include_router(loans.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
