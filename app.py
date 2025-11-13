import os
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import threading
import time

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_from_directory, abort
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



def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return u


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_images(files):
    saved = []
    for f in files[:MAX_FILES]:
        if f and f.filename and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            unique = f"{timestamp}_{fname}"
            f.save(UPLOAD_DIR / unique)
            saved.append(unique)
    return saved


def schedule_delete(post_id):
    def _delete():
        time.sleep(DELETE_DELAY_SECONDS)
        conn = get_db()
        post = conn.execute(
            "SELECT id FROM posts WHERE id = ? AND status = 'pending_delete'",
            (post_id,)
        ).fetchone()

        if post:
            imgs = conn.execute(
                "SELECT filename FROM images WHERE post_id = ?",
                (post_id,)
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

@app.route("/")
def home():
    user = current_user()
    conn = get_db()

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

        posts = conn.execute(sql, args).fetchall()
        enriched = []
        for p in posts:
            imgs = conn.execute(
                "SELECT filename FROM images WHERE post_id = ?",
                (p["id"],),
            ).fetchall()
            enriched.append({**dict(p), "images": [r["filename"] for r in imgs]})
        return enriched

    found_posts = fetch("found")
    lost_posts = fetch("lost")
    conn.close()
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

    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

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

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name,enrollment,phone,hostel,email,password_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                name,
                enrollment,
                phone,
                hostel,
                email,
                generate_password_hash(password),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        flash("Email already registered.", "error")
        conn.close()
        return redirect(url_for("home"))

    u = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

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

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
    """
    INSERT INTO posts (user_id,kind,item_name,description,category,place,name,enrollment,phone,hostel,created_at)
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
        datetime.utcnow().isoformat(),
    ),
)

    post_id = cur.lastrowid

    saved = save_images(files)
    for fn in saved:
        cur.execute("INSERT INTO images (post_id, filename) VALUES (?,?)", (post_id, fn))

    conn.commit()
    conn.close()

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

    conn = get_db()
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

    if not post or post["user_id"] != u["id"]:
        conn.close()
        flash("Not allowed.", "error")
        return redirect(url_for("home"))

    if post["status"] == "pending_delete":
        conn.close()
        flash("Deletion already in progress.", "info")
        return redirect(url_for("home"))

    delete_at = (datetime.utcnow() + timedelta(seconds=DELETE_DELAY_SECONDS)).isoformat()
    conn.execute(
        "UPDATE posts SET status='pending_delete', delete_at=? WHERE id=?",
        (delete_at, post_id),
    )
    conn.commit()
    conn.close()

    schedule_delete(post_id)
    flash("Deletion started. The post will be removed in 60 seconds.", "warning")
    return redirect(url_for("home"))
from markupsafe import Markup

@app.context_processor
def inject_helpers():
    def render_cards(posts, tab_kind):
        out = []
        for p in posts:
            badge = "badge-found" if p["kind"] == "found" else "badge-lost"
            owner = p["user_id"] == session.get("uid")
            pending = p["status"] == "pending_delete"

            delete_eta = 0
            if pending and p.get("delete_at"):
                try:
                    delete_eta = int(datetime.fromisoformat(p["delete_at"]).timestamp())
                except Exception:
                    delete_eta = 0

            if owner:
                label = "Claimed" if p["kind"] == "found" else "Found"
                if pending:
                    btn_html = f"<div class='text-warning'>Deleting in <span data-delete-eta='{delete_eta}'></span>…</div>"
                else:
                    btn_html = f"""
                    <form method='post' action='{url_for('begin_delete', post_id=p['id'])}' class='d-flex gap-2 align-items-center'>
                      <input type='password' name='password' placeholder='Confirm password' class='form-control form-control-sm' required style='max-width:220px;'>
                      <button class='btn btn-outline-light btn-sm'>{label}</button>
                    </form>
                    <div class='form-text muted'>After confirmation, the post will auto-delete in 60s.</div>
                    """
            else:
                btn_html = ""

            images_html = "".join(
                f"<div class='col-4'><img class='w-100' src='{url_for('uploaded_file', filename=fn)}' alt='item image'></div>"
                for fn in p["images"]
            )

            out.append(f"""
            <div class='card mb-3'>
              <div class='card-body'>
                <div class='d-flex justify-content-between align-items-start'>
                     <h5 class='card-title mb-1'>{p['item_name']}</h5>
                     <div class='d-flex gap-2'>
                        <span class='badge {badge}'>{p['kind'].upper()}</span>
                        <span class='badge bg-secondary'>{p.get('category','Other')}</span>
                     </div>
                </div>

                <p class='muted mb-2'>{p.get('description') or ''}</p>
                <div class='row image-grid g-2 mb-2'>
                  {images_html}
                </div>
                <div class='small muted'>
                    <strong>Contact:</strong> {p['name']} · Enroll: {p['enrollment']} · Phone: <a class='link-light' href='tel:{p['phone']}'>{p['phone']}</a> · Hostel: {p['hostel']}<br>
                    <strong>Place:</strong> {p.get('place','Other')} · <strong>Posted:</strong> {p['created_at']}
                </div>
                <div class='mt-2'>
                  {btn_html}
                </div>
              </div>
            </div>
            """)

        if not posts:
            out.append("<div class='text-center text-muted py-5'>No posts yet.</div>")

        return Markup("\n".join(out))

    return dict(render_cards=render_cards)
if __name__ == "__main__":
    app.run(debug=True)
