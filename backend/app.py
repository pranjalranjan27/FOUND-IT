"""
Found IT â€” Flask REST API

All routes return JSON. No Jinja templates.
The frontend is a static HTML/JS/CSS client that consumes these endpoints.
"""

import json
import sqlite3  # noqa: F401 â€” used for IntegrityError in SQLite mode
from datetime import datetime, timezone
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
    CATEGORIES,
    PLACES,
    COMMUNITIES,
    SECRET_KEY,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    SESSION_TYPE,
)
from .database import get_db, close_db, init_db, adapt_query, get_cursor


def create_app():
    """Application factory â€” creates and configures the Flask app."""

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

    # â”€â”€ Lifecycle hooks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    app.teardown_appcontext(close_db)

    # â”€â”€ Startup tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    with app.app_context():
        init_db()

    # â”€â”€ Frontend serving â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @app.route("/")
    def index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(str(UPLOAD_DIR), filename)

    # â”€â”€ Database helpers (abstract SQLite / PostgreSQL differences) â”€â”€â”€

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

    # â”€â”€ API: Meta â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @app.route("/api/meta")
    def api_meta():
        return jsonify(ok=True, data={
            "categories": CATEGORIES,
            "places": PLACES,
            "communities": COMMUNITIES,
        })

    # â”€â”€ API: Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Google OAuth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # â”€â”€ API: Posts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            cc = _exec(db,
                "SELECT COUNT(*) as cnt FROM claims WHERE post_id = ? AND status = 'pending'",
                (p["id"],), fetchone=True
            )
            claim_count = cc["cnt"] if cc else 0

            post_dict = _post_dict(p, [r["filename"] for r in imgs], claim_count)
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
            cc = _exec(db,
                "SELECT COUNT(*) as cnt FROM claims WHERE post_id = ? AND status = 'pending'",
                (p["id"],), fetchone=True
            )
            claim_count = cc["cnt"] if cc else 0
            result.append(_post_dict(p, [r["filename"] for r in imgs], claim_count))

        return jsonify(ok=True, data={"posts": result})

    @app.route("/api/posts/<int:post_id>/status", methods=["POST"])
    def api_update_status(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        body = request.get_json(silent=True) or {}
        new_status = body.get("status", "").strip()

        if new_status not in ("active", "closed"):
            return jsonify(ok=False, error="Invalid status."), 400

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)

        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        if post["status"] == "closed":
            return jsonify(ok=False, error="Post is already closed."), 409

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

        now = datetime.now(timezone.utc).isoformat()

        post_id = _exec_insert(db,
            """
            INSERT INTO posts (user_id,kind,item_name,description,category,place,
                               community,name,phone,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                u["id"], kind, item_name, description, category, place,
                community, name, phone, now,
            ),
        )

        saved = _save_images(real_files)
        for fn in saved:
            _exec(db,
                "INSERT INTO images (post_id, filename) VALUES (?,?)", (post_id, fn)
            )

        # Audit log
        _audit_log(db, post_id, uid, "ITEM_CREATED", {"kind": kind, "item_name": item_name})

        # Activity log for post creator
        event_type = "item_created_found" if kind == "found" else "item_created_lost"
        _activity_log(db, uid, event_type,
            f"You posted a {kind} item: \"{item_name}\"",
            {"post_id": post_id, "kind": kind, "item_name": item_name})

        db.commit()
        return jsonify(ok=True, data={"post_id": post_id})

    # â”€â”€ API: Post close (owner only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @app.route("/api/posts/<int:post_id>/close", methods=["POST"])
    def api_close_post(post_id):
        """Owner manually closes a post (e.g. found it themselves)."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)

        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        if post["status"] == "closed":
            return jsonify(ok=False, error="Post is already closed."), 409

        # Reject all pending claims
        _exec(db,
            "UPDATE claims SET status = 'rejected' WHERE post_id = ? AND status = 'pending'",
            (post_id,),
        )
        _exec(db, "UPDATE posts SET status = 'closed' WHERE id = ?", (post_id,))

        _audit_log(db, post_id, uid, "ITEM_CLOSED", {"reason": "owner_manual_close"})

        db.commit()
        return jsonify(ok=True)

    # â”€â”€ API: Claims â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

        if post["status"] == "closed":
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

        now = datetime.now(timezone.utc).isoformat()

        # Determine request type based on post kind
        request_type = "return" if post["kind"] == "lost" else "claim"

        claim_id = _exec_insert(db,
            """
            INSERT INTO claims (post_id, claimant_user_id, claimant_name, claimant_email,
                                claimant_phone, message, status, request_type, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                post_id, uid, name, email, phone or None, message,
                "pending", request_type, now,
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

        # Update post status to claim_requested if currently active
        if post["status"] == "active":
            _exec(db, "UPDATE posts SET status = 'claim_requested' WHERE id = ?", (post_id,))

        _audit_log(db, post_id, uid, "CLAIM_REQUESTED", {"claim_id": claim_id, "request_type": request_type})

        # Activity mirroring: log for both users
        item_name = post["item_name"]
        meta = {"post_id": post_id, "claim_id": claim_id, "item_name": item_name}
        if request_type == "claim":
            _activity_log(db, uid, "claim_submitted",
                f"You submitted a claim for \"{item_name}\"", meta)
            _activity_log(db, post["user_id"], "claim_received",
                f"New claim received for \"{item_name}\"", meta)
        else:
            _activity_log(db, uid, "return_submitted",
                f"You submitted a return request for \"{item_name}\"", meta)
            _activity_log(db, post["user_id"], "return_received",
                f"New return request received for \"{item_name}\"", meta)

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
                "request_type": c.get("request_type", "claim") if hasattr(c, 'get') else (c["request_type"] if "request_type" in c.keys() else "claim"),
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

        # Approve this claim
        _exec(db, "UPDATE claims SET status = 'approved' WHERE id = ?", (claim_id,))
        # Auto-close the post
        _exec(db, "UPDATE posts SET status = 'closed' WHERE id = ?", (claim["post_id"],))
        # Reject all other pending claims on the same post
        _exec(db,
            "UPDATE claims SET status = 'rejected' WHERE post_id = ? AND id != ? AND status = 'pending'",
            (claim["post_id"], claim_id),
        )

        _audit_log(db, claim["post_id"], uid, "CLAIM_APPROVED", {
            "claim_id": claim_id,
            "claimant_name": claim["claimant_name"],
        })

        # Activity mirroring
        item_name = post["item_name"]
        req_type = claim.get("request_type", "claim") if hasattr(claim, 'get') else (claim["request_type"] if "request_type" in claim.keys() else "claim")
        meta = {"post_id": claim["post_id"], "claim_id": claim_id, "item_name": item_name}
        if req_type == "return":
            _activity_log(db, uid, "return_approved",
                f'You approved the return request for "{item_name}"', meta)
            _activity_log(db, claim["claimant_user_id"], "return_approved_claimant",
                f'Your return request was approved for "{item_name}"', meta)
        else:
            _activity_log(db, uid, "claim_approved",
                f'You approved the claim for "{item_name}"', meta)
            _activity_log(db, claim["claimant_user_id"], "claim_approved_claimant",
                f'Your claim was approved for "{item_name}"', meta)

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

        # If no remaining pending claims, revert post status to active
        remaining = _exec(db,
            "SELECT COUNT(*) as cnt FROM claims WHERE post_id = ? AND status = 'pending' AND id != ?",
            (claim["post_id"], claim_id), fetchone=True
        )
        if remaining and remaining["cnt"] == 0:
            _exec(db, "UPDATE posts SET status = 'active' WHERE id = ?", (claim["post_id"],))

        _audit_log(db, claim["post_id"], uid, "CLAIM_REJECTED", {"claim_id": claim_id})

        # Activity mirroring
        item_name = post["item_name"]
        req_type = claim.get("request_type", "claim") if hasattr(claim, 'get') else (claim["request_type"] if "request_type" in claim.keys() else "claim")
        meta = {"post_id": claim["post_id"], "claim_id": claim_id, "item_name": item_name}
        if req_type == "return":
            _activity_log(db, uid, "return_rejected",
                f'You rejected the return request for "{item_name}"', meta)
            _activity_log(db, claim["claimant_user_id"], "return_rejected_claimant",
                f'Your return request was rejected for "{item_name}"', meta)
        else:
            _activity_log(db, uid, "claim_rejected",
                f'You rejected the claim for "{item_name}"', meta)
            _activity_log(db, claim["claimant_user_id"], "claim_rejected_claimant",
                f'Your claim was rejected for "{item_name}"', meta)

        db.commit()
        return jsonify(ok=True)

    # â”€â”€ API: Audit log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @app.route("/api/posts/<int:post_id>/audit")
    def api_audit_log(post_id):
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (post_id,), fetchone=True)
        if not post or post["user_id"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        logs = _exec(db,
            "SELECT * FROM audit_logs WHERE post_id = ? ORDER BY created_at DESC",
            (post_id,), fetchall=True
        )

        result = []
        for log in logs:
            result.append({
                "id": log["id"],
                "post_id": log["post_id"],
                "actor_user_id": log["actor_user_id"],
                "action": log["action"],
                "metadata": log["metadata"],
                "created_at": log["created_at"],
            })

        return jsonify(ok=True, data={"audit_logs": result})

    # ── API: Activity feed ──────────────────────────────────────────────

    @app.route("/api/activity")
    def api_activity():
        """Return the current user's activity log, newest first."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        filt = request.args.get("filter", "all").strip()
        db = get_db()

        # Map filter values to event_type prefixes
        filter_map = {
            "found_posts": ("item_created_found",),
            "lost_posts": ("item_created_lost",),
            "claims": ("claim_submitted", "claim_received", "claim_approved", "claim_approved_claimant", "claim_rejected", "claim_rejected_claimant"),
            "returns": ("return_submitted", "return_received", "return_approved", "return_approved_claimant", "return_rejected", "return_rejected_claimant"),
            "contact": ("contact_requested", "contact_received", "contact_shared", "contact_shared_to"),
        }

        if filt in filter_map:
            placeholders = ",".join(["?" for _ in filter_map[filt]])
            sql = f"SELECT * FROM activity_logs WHERE user_id = ? AND event_type IN ({placeholders}) ORDER BY created_at DESC LIMIT 100"
            params = [uid] + list(filter_map[filt])
        else:
            sql = "SELECT * FROM activity_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 100"
            params = [uid]

        logs = _exec(db, sql, params, fetchall=True)

        result = []
        for log in logs:
            result.append({
                "id": log["id"],
                "event_type": log["event_type"],
                "message": log["message"],
                "metadata": log["metadata"],
                "created_at": log["created_at"],
            })

        return jsonify(ok=True, data={"activities": result})

    # ── API: Contact exchange ───────────────────────────────────────────

    @app.route("/api/contact/request", methods=["POST"])
    def api_contact_request():
        """Request contact info from the other party after claim approval."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        claim_id = request.json.get("claim_id") if request.is_json else request.form.get("claim_id")
        if not claim_id:
            return jsonify(ok=False, error="claim_id is required."), 400

        db = get_db()
        claim = _exec(db, "SELECT * FROM claims WHERE id = ?", (claim_id,), fetchone=True)
        if not claim or claim["status"] != "approved":
            return jsonify(ok=False, error="Only approved claims allow contact requests."), 400

        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (claim["post_id"],), fetchone=True)
        if not post:
            return jsonify(ok=False, error="Post not found."), 404

        # Determine who is requesting and who receives
        poster_id = post["user_id"]
        claimant_id = claim["claimant_user_id"]

        if uid == poster_id:
            requested_to = claimant_id
        elif uid == claimant_id:
            requested_to = poster_id
        else:
            return jsonify(ok=False, error="Not allowed."), 403

        # Check for existing pending request
        existing = _exec(db,
            "SELECT id FROM contact_requests WHERE claim_id = ? AND requested_by = ? AND status = 'pending'",
            (claim_id, uid), fetchone=True
        )
        if existing:
            return jsonify(ok=False, error="You already have a pending contact request."), 409

        now = datetime.now(timezone.utc).isoformat()
        _exec(db,
            "INSERT INTO contact_requests (claim_id, requested_by, requested_to, status, created_at) VALUES (?,?,?,?,?)",
            (claim_id, uid, requested_to, "pending", now),
        )

        item_name = post["item_name"]
        meta = {"post_id": post["id"], "claim_id": claim_id, "item_name": item_name}
        _activity_log(db, uid, "contact_requested",
            f"You requested contact info for \"{item_name}\"", meta)
        _activity_log(db, requested_to, "contact_received",
            f"Someone requested your contact info for \"{item_name}\"", meta)

        db.commit()
        return jsonify(ok=True)

    @app.route("/api/contact/<int:contact_id>/share", methods=["POST"])
    def api_contact_share(contact_id):
        """Share your contact info with the requester."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        cr = _exec(db, "SELECT * FROM contact_requests WHERE id = ?", (contact_id,), fetchone=True)
        if not cr or cr["requested_to"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        _exec(db, "UPDATE contact_requests SET status = 'shared' WHERE id = ?", (contact_id,))

        claim = _exec(db, "SELECT * FROM claims WHERE id = ?", (cr["claim_id"],), fetchone=True)
        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (claim["post_id"],), fetchone=True) if claim else None
        item_name = post["item_name"] if post else "an item"

        meta = {"claim_id": cr["claim_id"], "contact_id": contact_id, "item_name": item_name}
        _activity_log(db, uid, "contact_shared",
            f"You shared your contact info for \"{item_name}\"", meta)
        _activity_log(db, cr["requested_by"], "contact_shared_to",
            f"Contact info was shared with you for \"{item_name}\"", meta)

        db.commit()
        return jsonify(ok=True)

    @app.route("/api/contact/<int:contact_id>/ignore", methods=["POST"])
    def api_contact_ignore(contact_id):
        """Ignore a contact request."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        cr = _exec(db, "SELECT * FROM contact_requests WHERE id = ?", (contact_id,), fetchone=True)
        if not cr or cr["requested_to"] != uid:
            return jsonify(ok=False, error="Not allowed."), 403

        _exec(db, "UPDATE contact_requests SET status = 'ignored' WHERE id = ?", (contact_id,))
        db.commit()
        return jsonify(ok=True)

    @app.route("/api/contact/<int:claim_id>/info")
    def api_contact_info(claim_id):
        """Get the other party's phone after contact is shared or claim approved."""
        uid = session.get("uid")
        if not uid:
            return jsonify(ok=False, error="Not signed in."), 401

        db = get_db()
        claim = _exec(db, "SELECT * FROM claims WHERE id = ?", (claim_id,), fetchone=True)
        if not claim or claim["status"] != "approved":
            return jsonify(ok=False, error="Contact info is only available for approved claims."), 400

        post = _exec(db, "SELECT * FROM posts WHERE id = ?", (claim["post_id"],), fetchone=True)
        if not post:
            return jsonify(ok=False, error="Post not found."), 404

        poster_id = post["user_id"]
        claimant_id = claim["claimant_user_id"]

        if uid != poster_id and uid != claimant_id:
            return jsonify(ok=False, error="Not allowed."), 403

        # Determine the other party
        if uid == poster_id:
            other_id = claimant_id
        else:
            other_id = poster_id

        # Check if contact has been shared
        shared = _exec(db,
            """SELECT id FROM contact_requests
               WHERE claim_id = ? AND status = 'shared'
               AND ((requested_by = ? AND requested_to = ?) OR (requested_by = ? AND requested_to = ?))""",
            (claim_id, uid, other_id, other_id, uid), fetchone=True
        )

        other_user = _exec(db, "SELECT * FROM users WHERE id = ?", (other_id,), fetchone=True)

        # Check if other user's phone is available on the post or claim
        other_phone = None
        has_contact = False

        if shared:
            has_contact = True
            if other_user and other_user["phone"]:
                other_phone = other_user["phone"]
            elif uid == poster_id:
                other_phone = claim["claimant_phone"]
            else:
                other_phone = post["phone"]
        else:
            # Even without explicit share, the claim always has claimant contact
            # and the post always has poster contact — check if phone exists
            if uid == poster_id and claim["claimant_phone"]:
                has_contact = True
                other_phone = claim["claimant_phone"]
            elif uid == claimant_id and post["phone"]:
                has_contact = True
                other_phone = post["phone"]

        # Check for pending contact request
        pending = _exec(db,
            "SELECT * FROM contact_requests WHERE claim_id = ? AND requested_to = ? AND status = 'pending'",
            (claim_id, uid), fetchone=True
        )

        return jsonify(ok=True, data={
            "has_contact": has_contact,
            "phone": other_phone,
            "other_name": other_user["name"] if other_user else claim["claimant_name"],
            "other_email": other_user["email"] if other_user else claim["claimant_email"],
            "pending_request": {"id": pending["id"]} if pending else None,
        })

    # ── Helpers (private) ─────────────────────────────────────────────────────────

    def _user_dict(u):
        """Convert a user Row to a safe dict (no password hash)."""
        return {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "phone": u["phone"],
            "community": u["community"],
        }

    def _post_dict(p, images, claim_count=0):
        """Convert a post Row to a clean API dict."""
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
            "claim_count": claim_count,
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

    def _audit_log(db, post_id, actor_user_id, action, meta=None):
        """Write an entry to the audit_logs table."""
        _exec(db,
            """
            INSERT INTO audit_logs (post_id, actor_user_id, action, metadata, created_at)
            VALUES (?,?,?,?,?)
            """,
            (
                post_id, actor_user_id, action,
                json.dumps(meta) if meta else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _activity_log(db, user_id, event_type, message, meta=None):
        """Write an entry to the user-facing activity_logs table."""
        _exec(db,
            """
            INSERT INTO activity_logs (user_id, event_type, message, metadata, created_at)
            VALUES (?,?,?,?,?)
            """,
            (
                user_id, event_type, message,
                json.dumps(meta) if meta else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return app

