"""
Found IT — Database Layer

Supports both SQLite (local development) and PostgreSQL (production).
The active backend is controlled by the DATABASE_URL environment variable:
  - If set → PostgreSQL via psycopg2
  - If unset → SQLite via sqlite3
"""

import sqlite3
from datetime import datetime, timezone

from flask import g

from .config import IS_POSTGRES, UPLOAD_DIR

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras
    from .config import DATABASE_URL
else:
    from .config import DATABASE_URI


# ── Connection management ────────────────────────────────────────────

def _pg_connect():
    """Return a new PostgreSQL connection with dict-like rows."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _pg_cursor(conn):
    """Return a cursor that produces dict-like rows."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def get_db():
    """Return a request-scoped database connection (stored on Flask g)."""
    if "db" not in g:
        if IS_POSTGRES:
            g.db = _pg_connect()
        else:
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
    if IS_POSTGRES:
        return _pg_connect()
    else:
        conn = sqlite3.connect(DATABASE_URI)
        conn.row_factory = sqlite3.Row
        return conn


def get_cursor(db):
    """Return an appropriate cursor for the active database backend."""
    if IS_POSTGRES:
        return _pg_cursor(db)
    else:
        return db.cursor()


# ── Placeholder helper ───────────────────────────────────────────────

def ph(index=None):
    """Return the parameter placeholder for the active DB backend.

    SQLite uses '?' and PostgreSQL uses '%s'.
    This helper is used internally; queries in app.py are rewritten
    via the execute wrapper.
    """
    return "%s" if IS_POSTGRES else "?"


def adapt_query(sql):
    """Convert '?' placeholders to '%s' for PostgreSQL."""
    if IS_POSTGRES:
        return sql.replace("?", "%s")
    return sql


# ── Schema ───────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist; migrate schema safely."""
    conn = _connect()

    if IS_POSTGRES:
        cur = _pg_cursor(conn)

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password_hash TEXT NOT NULL,
                community TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                kind TEXT CHECK(kind IN ('found','lost')) NOT NULL,
                item_name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                place TEXT,
                community TEXT,
                name TEXT NOT NULL,
                phone TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
            """
        )

        # Safe migration: remove delete_at column if it exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'posts' AND column_name = 'delete_at'
        """)
        if cur.fetchone():
            cur.execute("ALTER TABLE posts DROP COLUMN delete_at")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL REFERENCES posts(id),
                filename TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL REFERENCES posts(id),
                claimant_user_id INTEGER,
                claimant_name TEXT NOT NULL,
                claimant_email TEXT NOT NULL,
                claimant_phone TEXT,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_files (
                id SERIAL PRIMARY KEY,
                claim_id INTEGER NOT NULL REFERENCES claims(id),
                filename TEXT NOT NULL,
                original_name TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_requests (
                id SERIAL PRIMARY KEY,
                claim_id INTEGER NOT NULL REFERENCES claims(id),
                requested_by INTEGER NOT NULL,
                requested_to INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )

        # Safe migration: add request_type column to claims if missing
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'claims' AND column_name = 'request_type'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE claims ADD COLUMN request_type TEXT DEFAULT 'claim'")

        conn.commit()
        cur.close()
        conn.close()

    else:
        # SQLite — original schema
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password_hash TEXT NOT NULL,
                community TEXT,
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
                community TEXT,
                name TEXT NOT NULL,
                phone TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # Safe migrations for existing SQLite databases
        cols = [r[1] for r in cur.execute("PRAGMA table_info(posts)").fetchall()]
        if "category" not in cols:
            cur.execute("ALTER TABLE posts ADD COLUMN category TEXT")
            cur.execute("UPDATE posts SET category = 'Other' WHERE category IS NULL")
        if "place" not in cols:
            cur.execute("ALTER TABLE posts ADD COLUMN place TEXT")
            cur.execute("UPDATE posts SET place = 'Other' WHERE place IS NULL")
        if "community" not in cols:
            cur.execute("ALTER TABLE posts ADD COLUMN community TEXT")

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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                claimant_user_id INTEGER,
                claimant_name TEXT NOT NULL,
                claimant_email TEXT NOT NULL,
                claimant_phone TEXT,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(post_id) REFERENCES posts(id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT,
                FOREIGN KEY(claim_id) REFERENCES claims(id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id INTEGER NOT NULL,
                requested_by INTEGER NOT NULL,
                requested_to INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(claim_id) REFERENCES claims(id)
            )
            """
        )

        # Safe migration: add request_type column to claims if missing
        claim_cols = [r[1] for r in cur.execute("PRAGMA table_info(claims)").fetchall()]
        if "request_type" not in claim_cols:
            cur.execute("ALTER TABLE claims ADD COLUMN request_type TEXT DEFAULT 'claim'")

        conn.commit()
        conn.close()
