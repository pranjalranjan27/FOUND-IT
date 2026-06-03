# 🧭 Found IT

**Found IT** is a **community-based Lost & Found platform** with a separated frontend/backend architecture.  
Post items you've *found* or *lost* in your community — campus, apartment complex, office, or any group — to help reunite belongings with their owners.

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
Both are served from a single `python run.py` command.

---

## 🚀 Features

### 🏘️ Community-Based
- Posts belong to **communities** (universities, apartments, offices, etc.)
- Search and filter scoped by community
- Promotes **local trust and relevance**

### 👤 Authentication
- Development: email/password login
- Production: **Microsoft OAuth / Azure AD** (UI-ready, backend pending)
- Session-based with Flask secure cookies

### 🎒 Lost & Found System
- Post items you've **found** or **lost** with:
  - Item name, description, category, location, community
  - Up to **3 image uploads** per post
- Separate tabs for Found and Lost items
- Post count badges on each tab

### 🔍 Search & Filter
- **Keyword search** across item names and descriptions
- **Community filter** — scoped to your community
- **Category filter** (Mobile, Laptop, Wallet, Keys, etc.)
- **Location filter** (Library, Cafeteria, Classroom, etc.)
- **URL persistence** — search state saved via `history.pushState()`
- Browser back/forward navigation works with search state

### 🕐 Smart Post Management
- Post owners can **mark items as claimed/found**
- **60-second countdown timer** before auto-deletion
- Orphaned deletions auto-recovered on server restart

### ✨ Modern Interface
- Dark charcoal theme with subtle blue accents
- Elevated cards with shadow depth
- **Image lightbox** — click thumbnails to view full-size
- **Image preview** before upload with remove buttons
- **Relative timestamps** ("3 h ago")
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
│   └── uploads/                ← User-uploaded images
│
├── frontend/
│   ├── index.html              ← Complete static page
│   ├── css/
│   │   └── style.css           ← Dark charcoal theme
│   └── js/
│       └── app.js              ← Fetch-based client logic
│
├── .gitignore
└── README.md
```

---

## 🛠️ Setup & Run

### Prerequisites
- **Python 3.10+**

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
| `GET` | `/api/meta` | Categories, locations, communities |
| `GET` | `/api/auth/session` | Current user info |
| `POST` | `/api/auth/login` | Login (JSON body) |
| `POST` | `/api/auth/register` | Register (JSON body) |
| `POST` | `/api/auth/logout` | Logout |
| `GET` | `/api/posts?kind=&q=&cat=&place=&community=` | List posts |
| `POST` | `/api/posts` | Create post (FormData) |
| `POST` | `/api/posts/<id>/delete` | Begin 60s deletion |
| `GET` | `/uploads/<filename>` | Serve uploaded images |

### Response Format
```json
{ "ok": true, "data": { ... } }
{ "ok": false, "error": "Error message" }
```

---

## 🗄️ Database

| Table | Purpose |
|-------|---------|
| `users` | Accounts (name, email, phone, community, password hash) |
| `posts` | Lost/found items (item details, community, contact, status) |
| `images` | Filenames linked to posts (up to 3 per post) |

The database is **auto-created** on the first run.

> The database layer is isolated in `backend/database.py`. PostgreSQL migration is a single-file change.

---

## 🔒 Security

- ✅ Password hashing (Werkzeug `pbkdf2:sha256`)
- ✅ Parameterized SQL queries (no SQL injection)
- ✅ `secure_filename()` for uploads
- ✅ HTML escaping in JS (`esc()` helper)
- ✅ Ownership validation before deletion
- ✅ 8 MB max upload size

---

## 🚀 Deployment

| Component | Recommended Host |
|-----------|-----------------|
| **Frontend** (`frontend/`) | Vercel, Netlify, GitHub Pages |
| **Backend** (`backend/` + `run.py`) | Render, Railway, Fly.io |

---

## 🔮 Roadmap

- **Microsoft OAuth / Azure AD** — institutional SSO login
- **PostgreSQL** — production database
- Claim request workflow (request → approve → resolved)
- Match suggestions (auto-match lost and found items)
- User profile with post history
- Email notifications for matching items
- Admin moderation panel

---

## 🔐 Developer Note: Authentication

> **Current:** Temporary email/password auth for development. Old accounts cleared on startup.
>
> **Future:** Microsoft OAuth (Azure AD). The frontend already shows "Continue with Microsoft" (disabled).
> Backend has placeholder route stubs in `backend/app.py`.

---

## 📄 License

This project is for educational purposes.
