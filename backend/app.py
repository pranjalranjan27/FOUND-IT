"""
Found IT — Flask REST API

All routes return JSON. No Jinja templates.
The frontend is a static HTML/JS/CSS client that consumes these endpoints.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from .config import (
    FRONTEND_DIR,
    UPLOAD_DIR,
    DATABASE_URI,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_FILES,
    MAX_CONTENT_MB,
    DELETE_DELAY_SECONDS,
    CATEGORIES,
    PLACES,
    SECRET_KEY,
)
from .database import get_db, close_db, init_db, cleanup_stale_deletes, reset_old_users


def create_app():
    """Application factory — creates and configures the Flask app."""

    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )

    app.config.update(
        SECRET_KEY=SECRET_KEY,
        MAX_CONTENT_LENGTH=MAX_CONTENT_MB * 1024 * 1024,
    )

    # ── Lifecycle hooks ──────────────────────────────────────────────

    app.teardown_appcontext(close_db)

    # ── Startup tasks ────────────────────────────────────────────────

    with app.app_context():
        init_db()
        cleanup_stale_deletes()
        reset_old_users()

    # ── Frontend serving ─────────────────────────────────────────────

    @app.route("/")
    def index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(str(UPLOAD_DIR), filename)

    # ── API: Meta ────────────────────────────────────────────────────

    @app.route("/api/meta")
    def api_meta():
        return jsonify(ok=True, data={
            "categories": CATEGORIES,
            "places": PLACES,
        })

    # ── API: Auth ────────────────────────────────────────────────────
    #
    # Temporary local auth (email + password).
    # Will be replaced by Microsoft OAuth / Azure AD once available.

    @app.route("/api/auth/session")
    def api_session():
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=True, data={"user": None})
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not u:
            session.clear()
            return jsonify(ok=True, data={"user": None})
        return jsonify(ok=True, data={"user": _user_dict(u)})

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        body = request.get_json(silent=True) or {}
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")

        db = get_db()
        u = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not u or not check_password_hash(u["password_hash"], password):
            return jsonify(ok=False, error="Invalid email or password."), 401

        session["uid"] = u["id"]
        return jsonify(ok=True, data={"user": _user_dict(u)})

    @app.route("/api/auth/register", methods=["POST"])
    def api_register():
        body = request.get_json(silent=True) or {}
        name = body.get("name", "").strip()
        email = body.get("email", "").strip().lower()
        enrollment = body.get("enrollment", "").strip()
        phone = body.get("phone", "").strip()
        hostel = body.get("hostel", "").strip()
        password = body.get("password", "")

        if not all([name, email, enrollment, phone, hostel, password]):
            return jsonify(ok=False, error="All fields are required."), 400

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name,enrollment,phone,hostel,email,password_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    name, enrollment, phone, hostel, email,
                    generate_password_hash(password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify(ok=False, error="Email already registered."), 409

        u = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        session["uid"] = u["id"]
        return jsonify(ok=True, data={"user": _user_dict(u)})

    @app.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        session.clear()
        return jsonify(ok=True)

    # ── Future: Microsoft OAuth ──────────────────────────────────────
    #
    # @app.route("/api/auth/microsoft")
    # def microsoft_login():
    #     """Redirect user to Microsoft OAuth consent page."""
    #     ...
    #
    # @app.route("/api/auth/callback")
    # def auth_callback():
    #     """Handle OAuth redirect, create/fetch user, set session."""
    #     ...

    # ── API: Posts ────────────────────────────────────────────────────

    @app.route("/api/posts")
    def api_posts():
        kind = request.args.get("kind", "found").strip()
        q = request.args.get("q", "").strip()
        cat = request.args.get("cat", "").strip()
        place = request.args.get("place", "").strip()

        db = get_db()
        sql = "SELECT * FROM posts WHERE kind = ?"
        args = [kind]

        if q:
            sql += " AND (item_name LIKE ? OR description LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if cat:
            sql += " AND category = ?"
            args.append(cat)
        if place:
            sql += " AND place = ?"
            args.append(place)

        sql += " ORDER BY created_at DESC"

        posts = db.execute(sql, args).fetchall()
        result = []
        for p in posts:
            imgs = db.execute(
                "SELECT filename FROM images WHERE post_id = ?", (p["id"],)
            ).fetchall()

            post_dict = {**dict(p), "images": [r["filename"] for r in imgs]}

            if p["status"] == "pending_delete" and p["delete_at"]:
                try:
                    post_dict["delete_eta_ts"] = int(
                        datetime.fromisoformat(p["delete_at"]).timestamp()
                    )
                except Exception:
                    post_dict["delete_eta_ts"] = 0
            else:
                post_dict["delete_eta_ts"] = 0

            result.append(post_dict)

        return jsonify(ok=True, data={"posts": result})

    @app.route("/api/posts", methods=["POST"])
    def api_create_post():
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="You need to login first."), 401

        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not u:
            return jsonify(ok=False, error="User not found."), 401

        kind = request.form.get("kind", "").strip()
        if kind not in ("found", "lost"):
            return jsonify(ok=False, error="Invalid post kind."), 400

        item_name = request.form.get("item_name", "").strip()
        description = request.form.get("description", "").strip()
        name = request.form.get("name", "").strip()
        enrollment = request.form.get("enrollment", "").strip()
        phone = request.form.get("phone", "").strip()
        hostel = request.form.get("hostel", "").strip()
        category = request.form.get("category", "Other").strip()
        place = request.form.get("place", "Other").strip()
        files = request.files.getlist("images")

        real_files = [f for f in files if f and f.filename]
        if len(real_files) > MAX_UPLOAD_FILES:
            return jsonify(ok=False, error=f"Maximum {MAX_UPLOAD_FILES} images allowed."), 400

        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO posts (user_id,kind,item_name,description,category,place,
                               name,enrollment,phone,hostel,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                u["id"], kind, item_name, description, category, place,
                name, enrollment, phone, hostel,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        post_id = cur.lastrowid

        saved = _save_images(real_files)
        for fn in saved:
            cur.execute(
                "INSERT INTO images (post_id, filename) VALUES (?,?)", (post_id, fn)
            )

        db.commit()
        return jsonify(ok=True, data={"post_id": post_id})

    @app.route("/api/posts/<int:post_id>/delete", methods=["POST"])
    def api_begin_delete(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="You need to login first."), 401

        db = get_db()
        post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        if post["status"] == "pending_delete":
            return jsonify(ok=False, error="Deletion already in progress."), 409

        delete_at = (
            datetime.now(timezone.utc) + timedelta(seconds=DELETE_DELAY_SECONDS)
        ).isoformat()
        db.execute(
            "UPDATE posts SET status='pending_delete', delete_at=? WHERE id=?",
            (delete_at, post_id),
        )
        db.commit()

        _schedule_delete(post_id)
        return jsonify(ok=True)

    # ── Helpers (private) ────────────────────────────────────────────

    def _user_dict(u):
        """Convert a user Row to a safe dict (no password hash)."""
        return {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "enrollment": u["enrollment"],
            "phone": u["phone"],
            "hostel": u["hostel"],
        }

    def _allowed_file(filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def _save_images(files):
        saved = []
        for f in files[:MAX_UPLOAD_FILES]:
            if f and f.filename and _allowed_file(f.filename):
                fname = secure_filename(f.filename)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                unique = f"{timestamp}_{fname}"
                f.save(UPLOAD_DIR / unique)
                saved.append(unique)
        return saved

    def _schedule_delete(post_id):
        """Background thread that deletes a post after DELETE_DELAY_SECONDS."""
        def _delete():
            time.sleep(DELETE_DELAY_SECONDS)
            conn = sqlite3.connect(DATABASE_URI)
            conn.row_factory = sqlite3.Row
            post = conn.execute(
                "SELECT id FROM posts WHERE id = ? AND status = 'pending_delete'",
                (post_id,),
            ).fetchone()

            if post:
                imgs = conn.execute(
                    "SELECT filename FROM images WHERE post_id = ?", (post_id,)
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

    return app
