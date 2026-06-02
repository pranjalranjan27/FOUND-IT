# 🧭 Found IT

**Found IT** is a campus-based **Lost & Found Web Application** with a separated frontend/backend architecture.  
Students can post items they've *found* or *lost* on campus, making it easy to reconnect belongings with their owners.

---

## 🏗️ Architecture

```
Browser (static HTML/JS/CSS)
        ↕  fetch()
Flask REST API (JSON responses)
        ↕
SQLite Database
```

The frontend is a **static client** — pure HTML, CSS, and vanilla JavaScript.  
The backend is a **Flask REST API** — no Jinja templates, only JSON endpoints.  
Both are served from a single `python run.py` command during development.

---

## 🚀 Features

### 👤 Authentication
- Local registration and login (any email accepted during development)
- Passwords stored with **bcrypt-level hashing** via Werkzeug
- Session-based login with Flask secure cookies
- 🔜 **Microsoft OAuth / Azure AD** integration planned for production

### 🎒 Lost & Found System
- Post items you've **found** or **lost** with:
  - Item name, description, category, place, hostel block
  - Up to **3 image uploads** per post
- Separate tabs for Found and Lost items
- Post count badges on each tab

### 🔍 Search & Filter
- **Keyword search** across item names and descriptions
- **Category filter** (Mobile, Laptop, Charger, Book, ID Card, etc.)
- **Place filter** (Library, Canteen, Lecture Hall, Parking, etc.)
- **URL persistence** — search state saved in URL via `history.pushState()`
- Browser back/forward navigation works with search state

### 🕐 Smart Post Management
- Post owners can **mark items as claimed/found**
- **60-second countdown timer** before auto-deletion
- Orphaned deletions auto-recovered on server restart

### ✨ Modern Interface
- Dark theme with **glassmorphic cards** and hover effects
- **Image lightbox** — click any thumbnail to view full-size
- **Image preview** before upload with remove buttons
- **Relative timestamps** ("3 h ago" instead of raw ISO dates)
- Toast notifications with auto-dismiss
- Loading spinner on form submission
- Responsive design optimized for mobile

---

## ⚙️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | Python 3.12, Flask 3.0 (REST API) |
| **Frontend** | HTML5, CSS3, JavaScript (ES6) |
| **UI Framework** | Bootstrap 5.3 |
| **Typography** | Google Fonts (Inter) |
| **Database** | SQLite 3 |
| **Auth** | Werkzeug password hashing + Flask sessions |

---

## 📁 Project Structure

```
Found IT/
├── run.py                      ← Entry point: starts everything
│
├── backend/
│   ├── __init__.py
│   ├── app.py                  ← Flask REST API (routes, helpers)
│   ├── config.py               ← Configuration (paths, constants)
│   ├── database.py             ← Database layer (schema, queries)
│   ├── requirements.txt        ← Python dependencies
│   ├── instance/
│   │   └── foundit.db          ← SQLite database (auto-created)
│   └── uploads/                ← User-uploaded images (gitignored)
│
├── frontend/
│   ├── index.html              ← Complete static page
│   ├── css/
│   │   └── style.css           ← Dark theme, animations, responsive
│   └── js/
│       └── app.js              ← Fetch-based client logic
│
├── .gitignore
└── README.md
```

---

## 🛠️ Setup & Run

### Prerequisites
- **Python 3.10+** installed on your system

### 1. Clone the repository
```bash
git clone https://github.com/pranjalranjan27/FOUND-IT.git
cd FOUND-IT
```

### 2. Create a virtual environment
```bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r backend/requirements.txt
```

### 5. Run the application
```bash
python run.py
```

### 6. Open in browser
Navigate to **http://127.0.0.1:5000**

---

## 🔌 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/meta` | Categories and places |
| `GET` | `/api/auth/session` | Current user info |
| `POST` | `/api/auth/login` | Login (JSON body) |
| `POST` | `/api/auth/register` | Register (JSON body) |
| `POST` | `/api/auth/logout` | Logout |
| `GET` | `/api/posts?kind=found&q=...&cat=...&place=...` | List posts |
| `POST` | `/api/posts` | Create post (FormData) |
| `POST` | `/api/posts/<id>/delete` | Begin 60s deletion |
| `GET` | `/uploads/<filename>` | Serve uploaded images |

### Response Format
```json
// Success
{ "ok": true, "data": { ... } }

// Failure
{ "ok": false, "error": "Error message" }
```

---

## 🗄️ Database

The app uses **SQLite** with 3 tables:

| Table | Purpose |
|-------|---------|
| `users` | Student accounts (name, email, enrollment, phone, hostel, password hash) |
| `posts` | Lost/found items (item details, contact info, status, timestamps) |
| `images` | Filenames linked to posts (up to 3 per post) |

The database is **auto-created** on the first run. No setup needed.

> **Future:** The database layer is isolated in `backend/database.py`, making PostgreSQL migration a single-file change.

---

## 🔒 Security Features

- ✅ Password hashing (Werkzeug `pbkdf2:sha256`)
- ✅ Parameterized SQL queries (no SQL injection)
- ✅ `secure_filename()` for uploaded files
- ✅ HTML escaping in JS (XSS prevention)
- ✅ Ownership validation before post deletion
- ✅ 8 MB max upload size

---

## 🚀 Deployment

The architecture is designed for separate hosting:

| Component | Recommended Host |
|-----------|-----------------|
| **Frontend** (`frontend/`) | Vercel, Netlify, GitHub Pages |
| **Backend** (`backend/` + `run.py`) | Render, Railway, Fly.io |

For separate deployment, add `flask-cors` to the backend and configure the frontend API base URL.

---

## 🔮 Future Scope

- **Microsoft OAuth / Azure AD login** (replace local auth with institutional SSO)
- **PostgreSQL migration** (swap `backend/database.py`)
- Claim request system (request → owner approves → resolved)
- User profile page with post history
- Email notifications for matching items
- Pagination for large post volumes
- Dark / light theme toggle
- Admin moderation panel

---

## 🔐 Developer Note: Authentication

> **Current status:** The app uses temporary local email/password authentication for development.
> Old test accounts are cleared on every server restart.
>
> **Future plan:** Replace local auth with **Microsoft OAuth (Azure AD)** once institutional SSO access is available.
> The backend has placeholder route stubs (`/api/auth/microsoft`, `/api/auth/callback`) in `backend/app.py`.
> The users table, session system, and auth endpoints are designed to work with either auth method.

---

## 📄 License

This project is for educational purposes.
