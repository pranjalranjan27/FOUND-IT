"""
Found IT — Application Configuration

All project constants, paths, and Flask settings live here.
To migrate to PostgreSQL later, swap DATABASE_URI.
"""

import os
from pathlib import Path

# ── Directory layout ─────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

INSTANCE_DIR = BACKEND_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

UPLOAD_DIR = BACKEND_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────

DATABASE_URI = INSTANCE_DIR / "foundit.db"

# ── File uploads ─────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_UPLOAD_FILES = 3
MAX_CONTENT_MB = 8

# ── Post deletion ───────────────────────────────────────────────────

DELETE_DELAY_SECONDS = 60

# ── Domain data ──────────────────────────────────────────────────────

CATEGORIES = [
    "Mobile", "Laptop", "Charger", "Book", "ID Card",
    "Wallet", "Keys", "Bag", "Earphones", "Power Bank",
    "Clothes", "Other",
]

PLACES = [
    "Library", "Canteen", "Hostel Gate", "Lecture Hall", "Ground",
    "Parking", "Computer Lab", "Bus Stop", "Auditorium", "Other",
]

# ── Flask settings ───────────────────────────────────────────────────

SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
