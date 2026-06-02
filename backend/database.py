"""
Found IT — Database Layer

All SQLite access is isolated here so a future PostgreSQL migration
only requires changing this single file.
"""

import sqlite3
from datetime import datetime, timezone

from flask import g

from .config import DATABASE_URI, UPLOAD_DIR


# ── Connection management ────────────────────────────────────────────

def get_db():
    """Return a request-scoped database connection (stored on Flask g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_URI)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    """Automatically close the DB connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _connect():
    """Direct connection outside of Flask request context."""
    conn = sqlite3.connect(DATABASE_URI)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ───────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist; migrate schema safely."""
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            enrollment TEXT NOT NULL,
            phone TEXT NOT NULL,
            hostel TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT CHECK(kind IN ('found','lost')) NOT NULL,
            item_name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            place TEXT,
            name TEXT NOT NULL,
            enrollment TEXT NOT NULL,
            phone TEXT NOT NULL,
            hostel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            delete_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    cols = [r[1] for r in cur.execute("PRAGMA table_info(posts)").fetchall()]

    if "category" not in cols:
        cur.execute("ALTER TABLE posts ADD COLUMN category TEXT")
        cur.execute("UPDATE posts SET category = 'Other' WHERE category IS NULL")

    if "place" not in cols:
        cur.execute("ALTER TABLE posts ADD COLUMN place TEXT")
        cur.execute("UPDATE posts SET place = 'Other' WHERE place IS NULL")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id)
        )
        """
    )

    conn.commit()
    conn.close()


# ── Startup maintenance ──────────────────────────────────────────────

def cleanup_stale_deletes():
    """Remove posts stuck in pending_delete past their delete_at time.

    Runs once at startup to recover from server restarts that killed
    in-flight delete timers.
    """
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    stale = conn.execute(
        "SELECT id FROM posts WHERE status = 'pending_delete' AND delete_at <= ?",
        (now,),
    ).fetchall()
    for post in stale:
        _delete_post_files(conn, post["id"])
        conn.execute("DELETE FROM images WHERE post_id = ?", (post["id"],))
        conn.execute("DELETE FROM posts WHERE id = ?", (post["id"],))
    if stale:
        conn.commit()
    conn.close()


def reset_old_users():
    """Clear all old test/dev user accounts on startup.

    This keeps the database clean while the project transitions from
    local auth to Microsoft OAuth.  Posts are preserved (they carry
    their own contact info), but orphaned user rows are removed.
    """
    conn = _connect()
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()


def _delete_post_files(conn, post_id):
    """Remove uploaded image files for a post."""
    imgs = conn.execute(
        "SELECT filename FROM images WHERE post_id = ?", (post_id,)
    ).fetchall()
    for img in imgs:
        try:
            (UPLOAD_DIR / img["filename"]).unlink(missing_ok=True)
        except Exception:
            pass
