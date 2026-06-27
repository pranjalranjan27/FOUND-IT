"""
Found IT — Flask REST API

All routes return JSON. No Jinja templates.
The frontend is a static HTML/JS/CSS client that consumes these endpoints.
"""

import sqlite3  # noqa: F401 — used for IntegrityError in SQLite mode
import threading
import time
from datetime import datetime, timedelta, timezone
from authlib.integrations.flask_client import OAuth
from flask_session import Session

from flask import Flask, jsonify, request, session, send_from_directory, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from .config import (
    FRONTEND_DIR,
    UPLOAD_DIR,
    IS_POSTGRES,
    ALLOWED_EXTENSIONS,
    CLAIM_ALLOWED_EXTENSIONS,
    MAX_UPLOAD_FILES,
    MAX_CLAIM_FILES,
    MAX_CONTENT_MB,
    DELETE_DELAY_SECONDS,
    CATEGORIES,
    PLACES,
    COMMUNITIES,
    SECRET_KEY,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    SESSION_TYPE,
)
from .database import get_db, close_db, init_db, cleanup_stale_deletes, reset_old_users, adapt_query, get_cursor, _connect


def create_app():
    """Application factory — creates and configures the Flask app."""

    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )

    app.config.update(
        SECRET_KEY=SECRET_KEY,
        SESSION_TYPE=SESSION_TYPE,
        MAX_CONTENT_LENGTH=MAX_CONTENT_MB * 1024 * 1024,
    )

    Session(app)

    oauth = OAuth(app)

    google = oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile"
        }
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

    # ── Database helpers (abstract SQLite / PostgreSQL differences) ───

    def _exec(db, sql, params=(), *, fetchone=False, fetchall=False):
        """Execute a SQL query, adapting placeholders for the active backend.

        Returns the cursor after execution. Use fetchone/fetchall kwargs
        for convenience so callers don't need to worry about cursor types.
        """
        q = adapt_query(sql)
        if IS_POSTGRES:
            cur = get_cursor(db)
            cur.execute(q, params)
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
            return cur
        else:
            result = db.execute(q, params)
            if fetchone:
                return result.fetchone()
            if fetchall:
                return result.fetchall()
            return result

    def _exec_insert(db, sql, params=()):
        """Execute an INSERT and return the new row's ID.

        Uses RETURNING id for PostgreSQL, cursor.lastrowid for SQLite.
        """
        q = adapt_query(sql)
        if IS_POSTGRES:
            cur = get_cursor(db)
            cur.execute(q + " RETURNING id", params)
            return cur.fetchone()["id"]
        else:
            cur = db.cursor()
            cur.execute(q, params)
            return cur.lastrowid

    # ── API: Meta ────────────────────────────────────────────────────

    @app.route("/api/meta")
    def api_meta():
        return jsonify(ok=True, data={
            "categories": CATEGORIES,
            "places": PLACES,
            "communities": COMMUNITIES,
        })

    # ── API: Auth ────────────────────────────────────────────────────
    #
    # Local auth (email + password) for development.
    # Google OAuth is the primary authentication method.

    @app.route("/api/auth/session")
    def api_session():
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=True, data={"user": None})
        db = get_db()
        u = _exec(db, "SELECT * FROM users WHERE id = ?", (uid,), fetchone=True)
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
        u = _exec(db, "SELECT * FROM users WHERE email = ?", (email,), fetchone=True)

        if not u or not check_password_hash(u["password_hash"], password):
            return jsonify(ok=False, error="Invalid email or password."), 401

        session["uid"] = u["id"]
        return jsonify(ok=True, data={"user": _user_dict(u)})

    @app.route("/api/auth/register", methods=["POST"])
    def api_register():
        body = request.get_json(silent=True) or {}
        name = body.get("name", "").strip()
        email = body.get("email", "").strip().lower()
        phone = body.get("phone", "").strip()
        password = body.get("password", "")
        community = body.get("community", "").strip() or None

        if not all([name, email, password]):
            return jsonify(ok=False, error="Name, email, and password are required."), 400

        db = get_db()
        try:
            _exec(db,
                "INSERT INTO users (name,email,phone,password_hash,community,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    name, email, phone or None,
                    generate_password_hash(password),
                    community,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower() or "integrity" in str(exc).lower():
                return jsonify(ok=False, error="Email already registered."), 409
            raise

        u = _exec(db, "SELECT * FROM users WHERE email = ?", (email,), fetchone=True)
        session["uid"] = u["id"]
        return jsonify(ok=True, data={"user": _user_dict(u)})

    @app.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        session.clear()
        return jsonify(ok=True)

    # ── Google OAuth ─────────────────────────────────────────────────

    @app.route("/auth/google")
    def google_login():
        redirect_uri = url_for("google_callback", _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route("/auth/google/callback")
    def google_callback():
        token = google.authorize_access_token()
        user_info = token.get("userinfo")

        if not user_info:
            return jsonify({"error": "Google authentication failed"}), 400

        email = user_info.get("email")
        name = user_info.get("name")

        db = get_db()
        existing = _exec(db,
            "SELECT * FROM users WHERE email = ?", (email,), fetchone=True
        )

        if not existing:
            _exec(db,
                """
                INSERT INTO users (name, email, phone, password_hash, community, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name, email, None, "google-oauth", None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()
            existing = _exec(db,
                "SELECT * FROM users WHERE email = ?", (email,), fetchone=True
            )

        session["uid"] = existing["id"]
        return redirect("/")

    @app.route("/auth/user")
    def auth_user():
        uid = session.get("uid")
        if not uid:
            return jsonify({"authenticated": False})

        db = get_db()
        user = _exec(db,
            "SELECT * FROM users WHERE id = ?", (uid,), fetchone=True
        )

        if not user:
            return jsonify({"authenticated": False})

        return jsonify({
            "authenticated": True,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
            }
        })

    @app.route("/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return jsonify(ok=True)

    # ── API: Posts ────────────────────────────────────────────────────

    @app.route("/api/posts")
    def api_posts():
        kind = request.args.get("kind", "found").strip()
        q = request.args.get("q", "").strip()
        cat = request.args.get("cat", "").strip()
        place = request.args.get("place", "").strip()
        community = request.args.get("community", "").strip()

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
        if community:
            sql += " AND community = ?"
            args.append(community)

        sql += " ORDER BY created_at DESC"

        posts = _exec(db, sql, args, fetchall=True)
        result = []
        for p in posts:
            imgs = _exec(db,
                "SELECT filename FROM images WHERE post_id = ?", (p["id"],), fetchall=True
            )

            post_dict = _post_dict(p, [r["filename"] for r in imgs])
            result.append(post_dict)

        return jsonify(ok=True, data={"posts": result})

    @app.route("/api/posts/mine")
    def api_my_posts():
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        posts = _exec(db,
            "SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC",
            (uid,), fetchall=True
        )

        result = []
        for p in posts:
            imgs = _exec(db,
                "SELECT filename FROM images WHERE post_id = ?", (p["id"],), fetchall=True
            )
            result.append(_post_dict(p, [r["filename"] for r in imgs]))

        return jsonify(ok=True, data={"posts": result})

    @app.route("/api/posts/<int:post_id>/status", methods=["POST"])
    def api_update_status(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        body = request.get_json(silent=True) or {}
        new_status = body.get("status", "").strip()

        if new_status not in ("active", "claimed", "resolved"):
            return jsonify(ok=False, error="Invalid status."), 400

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)

        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        if post["status"] == "pending_delete":
            return jsonify(ok=False, error="Post is being deleted."), 409

        _exec(db, "UPDATE posts SET status = ? WHERE id = ?", (new_status, post_id))
        db.commit()
        return jsonify(ok=True, data={"status": new_status})

    @app.route("/api/posts", methods=["POST"])
    def api_create_post():
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="You need to sign in first."), 401

        db = get_db()
        u = _exec(db, "SELECT * FROM users WHERE id = ?", (uid,), fetchone=True)
        if not u:
            return jsonify(ok=False, error="User not found."), 401

        kind = request.form.get("kind", "").strip()
        if kind not in ("found", "lost"):
            return jsonify(ok=False, error="Invalid post kind."), 400

        item_name = request.form.get("item_name", "").strip()
        description = request.form.get("description", "").strip()
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        category = request.form.get("category", "Other").strip()
        place = request.form.get("place", "Other").strip()
        community = request.form.get("community", "").strip() or None
        files = request.files.getlist("images")

        if not item_name:
            return jsonify(ok=False, error="Item name is required."), 400

        real_files = [f for f in files if f and f.filename]
        if len(real_files) > MAX_UPLOAD_FILES:
            return jsonify(ok=False, error=f"Maximum {MAX_UPLOAD_FILES} images allowed."), 400

        post_id = _exec_insert(db,
            """
            INSERT INTO posts (user_id,kind,item_name,description,category,place,
                               community,name,phone,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                u["id"], kind, item_name, description, category, place,
                community, name, phone,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        saved = _save_images(real_files)
        for fn in saved:
            _exec(db,
                "INSERT INTO images (post_id, filename) VALUES (?,?)", (post_id, fn)
            )

        db.commit()
        return jsonify(ok=True, data={"post_id": post_id})

    @app.route("/api/posts/<int:post_id>/delete", methods=["POST"])
    def api_begin_delete(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="You need to sign in first."), 401

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)

        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        if post["status"] == "pending_delete":
            return jsonify(ok=False, error="Deletion already in progress."), 409

        delete_at = (
            datetime.now(timezone.utc) + timedelta(seconds=DELETE_DELAY_SECONDS)
        ).isoformat()
        _exec(db,
            "UPDATE posts SET status='pending_delete', delete_at=? WHERE id=?",
            (delete_at, post_id),
        )
        db.commit()

        _schedule_delete(post_id)
        return jsonify(ok=True)

    # ── API: Claims ──────────────────────────────────────────────────

    @app.route("/api/posts/<int:post_id>/claim", methods=["POST"])
    def api_submit_claim(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="You need to sign in first."), 401

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)
        if not post:
            return jsonify(ok=False, error="Post not found."), 404

        if post["user_id"] == uid:
            return jsonify(ok=False, error="You cannot claim your own post."), 400

        if post["status"] != "active":
            return jsonify(ok=False, error="This item is no longer available for claims."), 400

        # Check for existing pending claim from this user
        existing = _exec(db,
            "SELECT id FROM claims WHERE post_id = ? AND claimant_user_id = ? AND status = 'pending'",
            (post_id, uid), fetchone=True
        )
        if existing:
            return jsonify(ok=False, error="You already have a pending claim on this item."), 409

        name = request.form.get("claimant_name", "").strip()
        email = request.form.get("claimant_email", "").strip()
        phone = request.form.get("claimant_phone", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email:
            return jsonify(ok=False, error="Name and email are required."), 400

        claim_id = _exec_insert(db,
            """
            INSERT INTO claims (post_id, claimant_user_id, claimant_name, claimant_email,
                                claimant_phone, message, status, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                post_id, uid, name, email, phone or None, message,
                "pending", datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Save proof files
        files = request.files.getlist("proof")
        real_files = [f for f in files if f and f.filename][:MAX_CLAIM_FILES]
        for f in real_files:
            ext = (f.filename.rsplit(".", 1)[1].lower()) if "." in f.filename else ""
            if ext in CLAIM_ALLOWED_EXTENSIONS:
                fname = secure_filename(f.filename)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                unique = f"claim_{timestamp}_{fname}"
                f.save(UPLOAD_DIR / unique)
                _exec(db,
                    "INSERT INTO claim_files (claim_id, filename, original_name) VALUES (?,?,?)",
                    (claim_id, unique, f.filename),
                )

        db.commit()
        return jsonify(ok=True, data={"claim_id": claim_id})

    @app.route("/api/claims/mine")
    def api_my_claims():
        """Return all claims submitted ON the current user's posts."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        claims = _exec(db,
            """
            SELECT c.*, p.item_name, p.kind, p.category
            FROM claims c
            JOIN posts p ON c.post_id = p.id
            WHERE p.user_id = ?
            ORDER BY c.created_at DESC
            """,
            (uid,), fetchall=True
        )

        result = []
        for c in claims:
            files = _exec(db,
                "SELECT filename, original_name FROM claim_files WHERE claim_id = ?",
                (c["id"],), fetchall=True
            )
            result.append({
                "id": c["id"],
                "post_id": c["post_id"],
                "item_name": c["item_name"],
                "item_kind": c["kind"],
                "item_category": c["category"],
                "claimant_name": c["claimant_name"],
                "claimant_email": c["claimant_email"],
                "claimant_phone": c["claimant_phone"],
                "message": c["message"],
                "status": c["status"],
                "created_at": c["created_at"],
                "files": [{"filename": f["filename"], "original_name": f["original_name"]} for f in files],
            })

        return jsonify(ok=True, data={"claims": result})

    @app.route("/api/claims/<int:claim_id>/approve", methods=["POST"])
    def api_approve_claim(claim_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        claim = _exec(db, "SELECT * FROM claims WHERE id = ?", (claim_id,), fetchone=True)
        if not claim:
            return jsonify(ok=False, error="Claim not found."), 404

        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (claim["post_id"],), fetchone=True)
        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        # Approve claim and resolve post
        _exec(db, "UPDATE claims SET status = 'approved' WHERE id = ?", (claim_id,))
        _exec(db, "UPDATE posts SET status = 'resolved' WHERE id = ?", (claim["post_id"],))
        # Reject other pending claims on the same post
        _exec(db,
            "UPDATE claims SET status = 'rejected' WHERE post_id = ? AND id != ? AND status = 'pending'",
            (claim["post_id"], claim_id),
        )
        db.commit()
        return jsonify(ok=True)

    @app.route("/api/claims/<int:claim_id>/reject", methods=["POST"])
    def api_reject_claim(claim_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        claim = _exec(db, "SELECT * FROM claims WHERE id = ?", (claim_id,), fetchone=True)
        if not claim:
            return jsonify(ok=False, error="Claim not found."), 404

        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (claim["post_id"],), fetchone=True)
        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        _exec(db, "UPDATE claims SET status = 'rejected' WHERE id = ?", (claim_id,))
        db.commit()
        return jsonify(ok=True)

    # ── Helpers (private) ────────────────────────────────────────────

    def _user_dict(u):
        """Convert a user Row to a safe dict (no password hash)."""
        return {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "phone": u["phone"],
            "community": u["community"],
        }

    def _post_dict(p, images):
        """Convert a post Row to a clean API dict."""
        delete_eta_ts = 0
        if p["status"] == "pending_delete" and p["delete_at"]:
            try:
                delete_eta_ts = int(
                    datetime.fromisoformat(p["delete_at"]).timestamp()
                )
            except Exception:
                pass

        return {
            "id": p["id"],
            "user_id": p["user_id"],
            "kind": p["kind"],
            "item_name": p["item_name"],
            "description": p["description"],
            "category": p["category"],
            "place": p["place"],
            "community": p["community"],
            "name": p["name"],
            "phone": p["phone"],
            "status": p["status"],
            "created_at": p["created_at"],
            "images": images,
            "delete_eta_ts": delete_eta_ts,
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
            conn = _connect()
            if IS_POSTGRES:
                from .database import get_cursor as _gc
                cur = _gc(conn)
                cur.execute(
                    "SELECT id FROM posts WHERE id = %s AND status = 'pending_delete'",
                    (post_id,),
                )
                post = cur.fetchone()
                if post:
                    cur.execute("SELECT filename FROM images WHERE post_id = %s", (post_id,))
                    imgs = cur.fetchall()
                    for img in imgs:
                        try:
                            (UPLOAD_DIR / img["filename"]).unlink(missing_ok=True)
                        except Exception:
                            pass
                    cur.execute("DELETE FROM images WHERE post_id = %s", (post_id,))
                    cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
                    conn.commit()
                cur.close()
            else:
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
