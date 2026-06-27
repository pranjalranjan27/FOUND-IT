"""
Found IT — Application Configuration

All project constants, paths, and Flask settings live here.
To migrate to PostgreSQL later, swap DATABASE_URI.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# ── Directory layout ─────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

INSTANCE_DIR = BACKEND_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

UPLOAD_DIR = BACKEND_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

# If DATABASE_URL is set (production / Supabase), use PostgreSQL.
# Otherwise fall back to the local SQLite file.
if DATABASE_URL:
    # Render sometimes provides postgres:// which psycopg2 needs as postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    IS_POSTGRES = True
else:
    DATABASE_URI = INSTANCE_DIR / "foundit.db"
    IS_POSTGRES = False

# ── File uploads ─────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CLAIM_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf"}
MAX_UPLOAD_FILES = 3
MAX_CLAIM_FILES = 3
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
    "Library", "Cafeteria", "Classroom", "Entrance / Gate",
    "Parking", "Lab", "Sports Area", "Transit Area",
    "Auditorium", "Hostel", "Other",
]

COMMUNITIES = [
    "Bennett University", "Delhi University", "KIIT",
    "IIT Delhi", "Amity University", "Manipal University",
    "Apartment Complex", "Office Campus", "Public",
]

# ── Flask settings ───────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

SESSION_TYPE = "filesystem"