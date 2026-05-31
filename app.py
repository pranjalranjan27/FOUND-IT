import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import threading
import time

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_from_directory, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DB_PATH = INSTANCE_DIR / "foundit.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_FILES = 3
DELETE_DELAY_SECONDS = 60

CATEGORIES = [
    "Mobile", "Laptop", "Charger", "Book", "ID Card",
    "Wallet", "Keys", "Bag", "Earphones", "Power Bank",
    "Clothes", "Other"
]

PLACES = [
    "Library", "Canteen", "Hostel Gate", "Lecture Hall", "Ground",
    "Parking", "Computer Lab", "Bus Stop", "Auditorium", "Other"
]

app = Flask(__name__, instance_path=str(INSTANCE_DIR))

app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET", "dev-secret-change-me"),
    UPLOAD_FOLDER=str(UPLOAD_DIR),
)

ALLOWED_EMAIL_DOMAIN = "bennett.edu.in"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB per request


# ── Database helpers ─────────────────────────────────────────────────

def get_db():
    """Return a request-scoped database connection (stored on Flask g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Automatically close the DB connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist; migrate schema safely."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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


init_db()


def cleanup_stale_deletes():
    """Remove posts stuck in pending_delete past their delete_at time.

    This runs once at startup to recover from server restarts that killed
    in-flight delete timers.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    stale = conn.execute(
        "SELECT id FROM posts WHERE status = 'pending_delete' AND delete_at <= ?",
        (now,),
    ).fetchall()
    for post in stale:
        imgs = conn.execute(
            "SELECT filename FROM images WHERE post_id = ?", (post["id"],)
        ).fetchall()
        for img in imgs:
            try:
                (UPLOAD_DIR / img["filename"]).unlink(missing_ok=True)
            except Exception:
                pass
        conn.execute("DELETE FROM images WHERE post_id = ?", (post["id"],))
        conn.execute("DELETE FROM posts WHERE id = ?", (post["id"],))
    if stale:
        conn.commit()
    conn.close()


cleanup_stale_deletes()


# ── Helpers ──────────────────────────────────────────────────────────

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_images(files):
    saved = []
    for f in files[:MAX_FILES]:
        if f and f.filename and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            unique = f"{timestamp}_{fname}"
            f.save(UPLOAD_DIR / unique)
            saved.append(unique)
    return saved


def schedule_delete(post_id):
    """Background thread that deletes a post after DELETE_DELAY_SECONDS.

    Uses a direct sqlite3 connection (not Flask g) because threads have
    no request context.
    """
    def _delete():
        time.sleep(DELETE_DELAY_SECONDS)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        post = conn.execute(
            "SELECT id FROM posts WHERE id = ? AND status = 'pending_delete'",
            (post_id,),
        ).fetchone()

        if post:
            imgs = conn.execute(
                "SELECT filename FROM images WHERE post_id = ?",
                (post_id,),
            ).fetchall()

            for img in imgs:
                try:
                    (UPLOAD_DIR / img["filename"]).unlink(missing_ok=True)
                except Exception:
                    pass

            conn.execute("DELETE FROM images WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.commit()

        conn.close()

    threading.Thread(target=_delete, daemon=True).start()


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def home():
    user = current_user()
    db = get_db()

    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()
    place = request.args.get("place", "").strip()

    def fetch(kind):
        sql = "SELECT * FROM posts WHERE kind = ?"
        args = [kind]

        if q:
            sql += " AND (item_name LIKE ? OR description LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]

        if cat:
            sql += " AND category = ?"
            args += [cat]

        if place:
            sql += " AND place = ?"
            args += [place]

        sql += " ORDER BY created_at DESC"

        posts = db.execute(sql, args).fetchall()
        enriched = []
        for p in posts:
            imgs = db.execute(
                "SELECT filename FROM images WHERE post_id = ?",
                (p["id"],),
            ).fetchall()
            post_dict = {**dict(p), "images": [r["filename"] for r in imgs]}

            # Precompute delete-countdown timestamp for the JS timer
            if p["status"] == "pending_delete" and p["delete_at"]:
                try:
                    post_dict["delete_eta_ts"] = int(
                        datetime.fromisoformat(p["delete_at"]).timestamp()
                    )
                except Exception:
                    post_dict["delete_eta_ts"] = 0
            else:
                post_dict["delete_eta_ts"] = 0

            enriched.append(post_dict)
        return enriched

    found_posts = fetch("found")
    lost_posts = fetch("lost")
    return render_template(
        "home.html",
        user=user,
        found_posts=found_posts,
        lost_posts=lost_posts,
        categories=CATEGORIES,
        places=PLACES,
    )


@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    db = get_db()
    u = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not u or not check_password_hash(u["password_hash"], password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("home"))

    session["uid"] = u["id"]
    flash("Logged in successfully.", "success")
    return redirect(url_for("home"))


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    enrollment = request.form.get("enrollment", "").strip()
    phone = request.form.get("phone", "").strip()
    hostel = request.form.get("hostel", "").strip()
    password = request.form.get("password", "")

    if not email.endswith("@" + ALLOWED_EMAIL_DOMAIN):
        flash(f"Use your student email (@{ALLOWED_EMAIL_DOMAIN}).", "error")
        return redirect(url_for("home"))

    if not all([name, email, enrollment, phone, hostel, password]):
        flash("All fields are required.", "error")
        return redirect(url_for("home"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (name,enrollment,phone,hostel,email,password_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                name,
                enrollment,
                phone,
                hostel,
                email,
                generate_password_hash(password),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        flash("Email already registered.", "error")
        return redirect(url_for("home"))

    u = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    session["uid"] = u["id"]
    flash("Account created and logged in.", "success")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


@app.route("/post/<kind>", methods=["POST"])
def create_post(kind):
    if kind not in ("found", "lost"):
        abort(404)

    u = current_user()
    if not u:
        flash("You need to login first.", "error")
        return redirect(url_for("home"))

    item_name = request.form.get("item_name", "").strip()
    description = request.form.get("description", "").strip()
    name = request.form.get("name", "").strip()
    enrollment = request.form.get("enrollment", "").strip()
    phone = request.form.get("phone", "").strip()
    hostel = request.form.get("hostel", "").strip()
    files = request.files.getlist("images")
    category = request.form.get("category", "Other").strip()
    place = request.form.get("place", "Other").strip()

    if len([f for f in files if f and f.filename]) > MAX_FILES:
        flash(f"You can upload up to {MAX_FILES} images.", "error")
        return redirect(url_for("home"))

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO posts (user_id,kind,item_name,description,category,place,
                           name,enrollment,phone,hostel,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            u["id"],
            kind,
            item_name,
            description,
            category,
            place,
            name,
            enrollment,
            phone,
            hostel,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    post_id = cur.lastrowid

    saved = save_images(files)
    for fn in saved:
        cur.execute(
            "INSERT INTO images (post_id, filename) VALUES (?,?)", (post_id, fn)
        )

    db.commit()

    flash("Posted successfully.", "success")
    return redirect(url_for("home"))


@app.route("/begin-delete/<int:post_id>", methods=["POST"])
def begin_delete(post_id):
    u = current_user()
    if not u:
        flash("You need to login first.", "error")
        return redirect(url_for("home"))

    password = request.form.get("password", "")

    if not check_password_hash(u["password_hash"], password):
        flash("Password incorrect.", "error")
        return redirect(url_for("home"))

    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

    if not post or post["user_id"] != u["id"]:
        flash("Not allowed.", "error")
        return redirect(url_for("home"))

    if post["status"] == "pending_delete":
        flash("Deletion already in progress.", "info")
        return redirect(url_for("home"))

    delete_at = (
        datetime.now(timezone.utc) + timedelta(seconds=DELETE_DELAY_SECONDS)
    ).isoformat()
    db.execute(
        "UPDATE posts SET status='pending_delete', delete_at=? WHERE id=?",
        (delete_at, post_id),
    )
    db.commit()

    schedule_delete(post_id)
    flash("Deletion started. The post will be removed in 60 seconds.", "warning")
    return redirect(url_for("home"))


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
