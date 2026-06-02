/* ================================================================
   Found IT — app.js
   Fetch-based frontend.  Communicates with Flask REST API.
   All rendering done in JavaScript — no Jinja dependency.
   ================================================================ */

/* ── Centralized API helper ──────────────────────────────────────── */

async function api(url, options = {}) {
  const defaults = { credentials: "same-origin" };
  if (options.json) {
    defaults.headers = { "Content-Type": "application/json" };
    defaults.body = JSON.stringify(options.json);
    defaults.method = options.method || "POST";
    delete options.json;
  }
  const res = await fetch(url, { ...defaults, ...options });
  return res.json();
}

/* ── Application state ───────────────────────────────────────────── */

const state = {
  user: null,
  categories: [],
  places: [],
};

/* ── HTML escaping (XSS prevention) ──────────────────────────────── */

function esc(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = String(str);
  return d.innerHTML;
}

/* ── Toast notifications (replaces Flask flash) ──────────────────── */

function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  const cls = type === "error" ? "danger" : type;
  const el = document.createElement("div");
  el.className = `alert alert-${cls} alert-dismissible fade show mt-2`;
  el.setAttribute("role", "alert");
  el.innerHTML = `${esc(message)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
  container.prepend(el);

  if (type === "success") {
    setTimeout(() => {
      el.style.transition = "opacity .3s ease, transform .3s ease";
      el.style.opacity = "0";
      el.style.transform = "translateY(-8px)";
      setTimeout(() => el.remove(), 300);
    }, 8000);
  }
}

/* ── Relative timestamps ("3 h ago") ─────────────────────────────── */

function timeAgo(dateStr) {
  const date = new Date(dateStr);
  if (isNaN(date)) return dateStr;
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + " min ago";
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + " h ago";
  const days = Math.floor(hours / 24);
  if (days < 7) return days + " d ago";
  if (days < 30) return Math.floor(days / 7) + " w ago";
  return date.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });
}

/* ── Card rendering ──────────────────────────────────────────────── */

function renderCard(p) {
  const isOwner = state.user && p.user_id === state.user.id;
  const isPending = p.status === "pending_delete";

  let cardClasses = "card mb-3";
  if (isPending) cardClasses += " card-pending";
  if (isOwner) cardClasses += " card-own";

  // Images
  let imagesHtml = "";
  if (p.images && p.images.length) {
    const imgItems = p.images.map(img =>
      `<div class="col-4 col-sm-4">
        <img class="w-100 lightbox-trigger"
             src="/uploads/${esc(img)}"
             alt="Photo of ${esc(p.item_name)}"
             loading="lazy">
      </div>`
    ).join("");
    imagesHtml = `<div class="row image-grid g-2 mb-2">${imgItems}</div>`;
  }

  // Owner actions
  let ownerHtml = "";
  if (isOwner) {
    if (isPending) {
      ownerHtml = `
        <div class="mt-2 pt-2 border-top border-secondary border-opacity-50">
          <div class="text-warning d-flex align-items-center gap-2">
            <span class="spinner-border spinner-border-sm" role="status"></span>
            Deleting in <span data-delete-eta="${p.delete_eta_ts || 0}"></span>&hellip;
          </div>
        </div>`;
    } else {
      const label = p.kind === "found" ? "Mark as Claimed" : "Mark as Found";
      ownerHtml = `
        <div class="mt-2 pt-2 border-top border-secondary border-opacity-50">
          <div class="d-flex gap-2 align-items-center flex-wrap">
            <button class="btn btn-outline-light btn-sm" onclick="handleDelete(${p.id})">${label}</button>
          </div>
          <div class="form-text muted mt-1">After confirmation, the post will auto-delete in 60 s.</div>
        </div>`;
    }
  }

  return `
    <div class="${cardClasses}">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start">
          <h5 class="card-title mb-1">${esc(p.item_name)}</h5>
          <div class="d-flex gap-2 flex-shrink-0 ms-2">
            <span class="badge ${p.kind === "found" ? "badge-found" : "badge-lost"}">${esc(p.kind.toUpperCase())}</span>
            <span class="badge bg-secondary">${esc(p.category || "Other")}</span>
          </div>
        </div>
        ${p.description ? `<p class="muted mb-2">${esc(p.description)}</p>` : ""}
        ${imagesHtml}
        <div class="small muted">
          <strong>Contact:</strong> ${esc(p.name)} &middot; Enroll: ${esc(p.enrollment)} &middot;
          Phone: <a class="link-light" href="tel:${esc(p.phone)}">${esc(p.phone)}</a> &middot;
          Hostel: ${esc(p.hostel)}<br>
          <strong>Place:</strong> ${esc(p.place || "Other")} &middot;
          <strong>Posted:</strong>
          <time class="timeago" datetime="${esc(p.created_at)}">${esc(p.created_at)}</time>
        </div>
        ${ownerHtml}
      </div>
    </div>`;
}

function renderEmptyState(kind) {
  if (kind === "found") {
    return `
      <div class="empty-state">
        <div class="empty-icon">📦</div>
        <h5>No found items posted yet</h5>
        <p>Found something on campus? Post it here to help reunite it with its owner.</p>
        <button class="btn btn-outline-success btn-sm" onclick="openPostModal('found')">Post a found item</button>
      </div>`;
  }
  return `
    <div class="empty-state">
      <div class="empty-icon">🔍</div>
      <h5>No lost items reported</h5>
      <p>Lost something? Post the details and someone on campus might have found it.</p>
      <button class="btn btn-outline-danger btn-sm" onclick="openPostModal('lost')">Report a lost item</button>
    </div>`;
}

/* ── Navbar rendering ────────────────────────────────────────────── */

function renderNavbar() {
  const nav = document.getElementById("navAuth");
  if (state.user) {
    nav.innerHTML = `
      <span class="me-2 d-none d-md-inline">Hi, ${esc(state.user.name)} (${esc(state.user.email)})</span>
      <span class="me-2 d-md-none">${esc(state.user.name)}</span>
      <button class="btn btn-outline-light btn-sm" id="logoutBtn">Logout</button>`;
    document.getElementById("logoutBtn").addEventListener("click", handleLogout);
  } else {
    nav.innerHTML = `<button class="btn btn-primary btn-sm" id="openLogin">Login / Register</button>`;
    document.getElementById("openLogin").addEventListener("click", () => {
      new bootstrap.Modal(document.getElementById("authModal")).show();
    });
  }
}

/* ── Populate select dropdowns from meta ─────────────────────────── */

function populateSelects() {
  const ids = ["filterCategory", "postCategory"];
  ids.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    // Keep the first <option> (placeholder) and remove the rest
    while (sel.options.length > (id.startsWith("filter") ? 1 : 0)) {
      sel.remove(sel.options.length - 1);
    }
    state.categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      sel.appendChild(opt);
    });
  });

  const placeIds = ["filterPlace", "postPlace"];
  placeIds.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    while (sel.options.length > (id.startsWith("filter") ? 1 : 0)) {
      sel.remove(sel.options.length - 1);
    }
    state.places.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p; opt.textContent = p;
      sel.appendChild(opt);
    });
  });
}

/* ── URL state management (history.pushState) ────────────────────── */

function getSearchParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    cat: params.get("cat") || "",
    place: params.get("place") || "",
  };
}

function setSearchParams(q, cat, place) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (cat) params.set("cat", cat);
  if (place) params.set("place", place);
  const qs = params.toString();
  const newUrl = qs ? `?${qs}` : window.location.pathname;
  history.pushState({}, "", newUrl);
}

/* ── Data loading ────────────────────────────────────────────────── */

async function loadPosts() {
  const { q, cat, place } = getSearchParams();
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (cat) params.set("cat", cat);
  if (place) params.set("place", place);

  const qs = params.toString();

  const [foundRes, lostRes] = await Promise.all([
    api(`/api/posts?kind=found${qs ? "&" + qs : ""}`),
    api(`/api/posts?kind=lost${qs ? "&" + qs : ""}`),
  ]);

  const foundPosts = foundRes.ok ? foundRes.data.posts : [];
  const lostPosts = lostRes.ok ? lostRes.data.posts : [];

  // Render found cards
  const foundContainer = document.getElementById("foundCards");
  foundContainer.innerHTML = foundPosts.length
    ? foundPosts.map(renderCard).join("")
    : renderEmptyState("found");

  // Render lost cards
  const lostContainer = document.getElementById("lostCards");
  lostContainer.innerHTML = lostPosts.length
    ? lostPosts.map(renderCard).join("")
    : renderEmptyState("lost");

  // Update badges
  const foundBadge = document.getElementById("foundBadge");
  const lostBadge = document.getElementById("lostBadge");
  if (foundPosts.length) {
    foundBadge.textContent = foundPosts.length;
    foundBadge.classList.remove("d-none");
  } else {
    foundBadge.classList.add("d-none");
  }
  if (lostPosts.length) {
    lostBadge.textContent = lostPosts.length;
    lostBadge.classList.remove("d-none");
  } else {
    lostBadge.classList.add("d-none");
  }

  // Activate timeago + countdowns after render
  setupTimeago();
  setupCountdowns();
}

/* ── Auth handlers ───────────────────────────────────────────────── */

async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const email = form.email.value.trim();
  const password = form.password.value;

  const res = await api("/api/auth/login", { json: { email, password } });

  if (res.ok) {
    state.user = res.data.user;
    bootstrap.Modal.getInstance(document.getElementById("authModal"))?.hide();
    renderNavbar();
    showToast("Logged in successfully.", "success");
    loadPosts(); // Re-render cards for ownership
    prefillPostForm();
  } else {
    const err = document.getElementById("authError");
    err.textContent = res.error || "Login failed.";
    err.classList.remove("d-none");
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const form = e.target;
  const body = {
    name: form.name.value.trim(),
    email: form.email.value.trim(),
    enrollment: form.enrollment.value.trim(),
    phone: form.phone.value.trim(),
    hostel: form.hostel.value.trim(),
    password: form.password.value,
  };

  const res = await api("/api/auth/register", { json: body });

  if (res.ok) {
    state.user = res.data.user;
    bootstrap.Modal.getInstance(document.getElementById("authModal"))?.hide();
    renderNavbar();
    showToast("Account created and logged in.", "success");
    loadPosts();
    prefillPostForm();
  } else {
    const err = document.getElementById("authError");
    err.textContent = res.error || "Registration failed.";
    err.classList.remove("d-none");
  }
}

async function handleLogout() {
  await api("/api/auth/logout", { method: "POST" });
  state.user = null;
  renderNavbar();
  showToast("Logged out.", "success");
  loadPosts();
}

/* ── Post creation ───────────────────────────────────────────────── */

function prefillPostForm() {
  if (!state.user) return;
  const u = state.user;
  const name = document.getElementById("postName");
  const enrollment = document.getElementById("postEnrollment");
  const phone = document.getElementById("postPhone");
  const hostel = document.getElementById("postHostel");
  if (name && !name.value) name.value = u.name || "";
  if (enrollment && !enrollment.value) enrollment.value = u.enrollment || "";
  if (phone && !phone.value) phone.value = u.phone || "";
  if (hostel && !hostel.value) hostel.value = u.hostel || "";
}

function openPostModal(kind) {
  if (!state.user) {
    const err = document.getElementById("authError");
    if (err) {
      err.textContent = "You need to login first.";
      err.classList.remove("d-none");
    }
    new bootstrap.Modal(document.getElementById("authModal")).show();
    return;
  }

  const form = document.getElementById("postForm");
  form.reset();
  document.getElementById("imagePreview").innerHTML = "";

  const isFound = kind === "found";
  document.getElementById("postModalTitle").textContent = isFound
    ? "Post a FOUND item" : "Post a LOST item";
  document.getElementById("postKind").value = kind;

  prefillPostForm();
  new bootstrap.Modal(document.getElementById("postModal")).show();
}
window.openPostModal = openPostModal;

async function handlePostSubmit(e) {
  e.preventDefault();

  const input = document.getElementById("imageInput");
  const files = Array.from(input.files || []);
  if (files.length > 3) {
    showToast("Please upload a maximum of 3 images.", "error");
    return;
  }
  const allowed = ["png", "jpg", "jpeg", "webp"];
  for (const f of files) {
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (!allowed.includes(ext)) {
      showToast("Only PNG, JPG, JPEG, or WEBP images are allowed.", "error");
      return;
    }
  }

  // Show spinner
  const btnText = document.querySelector("#postSubmitBtn .btn-text");
  const spinner = document.getElementById("postSpinner");
  if (btnText) btnText.textContent = "Posting…";
  if (spinner) spinner.classList.remove("d-none");

  const form = document.getElementById("postForm");
  const formData = new FormData(form);

  try {
    const res = await fetch("/api/posts", {
      method: "POST",
      credentials: "same-origin",
      body: formData,
    });
    const data = await res.json();

    if (data.ok) {
      bootstrap.Modal.getInstance(document.getElementById("postModal"))?.hide();
      showToast("Posted successfully.", "success");
      loadPosts();
    } else {
      showToast(data.error || "Post failed.", "error");
    }
  } catch (err) {
    showToast("Network error. Please try again.", "error");
  } finally {
    if (btnText) btnText.textContent = "Post";
    if (spinner) spinner.classList.add("d-none");
  }
}

/* ── Post deletion ───────────────────────────────────────────────── */

async function handleDelete(postId) {
  if (!confirm("Are you sure? The post will be deleted in 60 seconds.")) return;

  const res = await api(`/api/posts/${postId}/delete`, { method: "POST" });
  if (res.ok) {
    showToast("Deletion started. The post will be removed in 60 seconds.", "warning");
    loadPosts();
  } else {
    showToast(res.error || "Could not delete.", "error");
  }
}
window.handleDelete = handleDelete;

/* ── Search & filters ────────────────────────────────────────────── */

function setupSearch() {
  const input = document.getElementById("searchInput");
  const btn = document.getElementById("searchBtn");
  const hiddenCat = document.getElementById("hiddenCat");
  const hiddenPlace = document.getElementById("hiddenPlace");

  // Restore from URL on initial load
  const { q, cat, place } = getSearchParams();
  if (q) input.value = q;
  if (cat) hiddenCat.value = cat;
  if (place) hiddenPlace.value = place;

  function doSearch() {
    const query = input.value.trim();
    const category = hiddenCat.value;
    const placeVal = hiddenPlace.value;
    setSearchParams(query, category, placeVal);
    loadPosts();
  }

  btn.addEventListener("click", doSearch);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });

  // Back/forward navigation
  window.addEventListener("popstate", () => {
    const p = getSearchParams();
    input.value = p.q;
    hiddenCat.value = p.cat;
    hiddenPlace.value = p.place;
    loadPosts();
  });
}

function setupFilters() {
  const btn = document.getElementById("filtersBtn");
  const modalEl = document.getElementById("filtersModal");
  if (!btn || !modalEl) return;

  const modal = new bootstrap.Modal(modalEl);
  const selCat = document.getElementById("filterCategory");
  const selPlace = document.getElementById("filterPlace");
  const hiddenCat = document.getElementById("hiddenCat");
  const hiddenPlace = document.getElementById("hiddenPlace");

  btn.addEventListener("click", () => {
    selCat.value = hiddenCat.value || "";
    selPlace.value = hiddenPlace.value || "";
    modal.show();
  });

  document.getElementById("filtersClear").addEventListener("click", () => {
    hiddenCat.value = "";
    hiddenPlace.value = "";
    selCat.value = "";
    selPlace.value = "";
  });

  document.getElementById("filtersApply").addEventListener("click", () => {
    hiddenCat.value = selCat.value || "";
    hiddenPlace.value = selPlace.value || "";
    modal.hide();
    const query = document.getElementById("searchInput").value.trim();
    setSearchParams(query, hiddenCat.value, hiddenPlace.value);
    loadPosts();
  });
}

/* ── Delete countdown timers ─────────────────────────────────────── */

function setupCountdowns() {
  document.querySelectorAll("[data-delete-eta]").forEach((el) => {
    const eta = parseInt(el.getAttribute("data-delete-eta"), 10);
    if (!eta) return;
    function tick() {
      const now = Math.floor(Date.now() / 1000);
      const remain = Math.max(0, eta - now);
      el.textContent = remain + "s";
      if (remain > 0) setTimeout(tick, 1000);
      else loadPosts(); // Refresh instead of full page reload
    }
    tick();
  });
}

/* ── Relative timestamps ─────────────────────────────────────────── */

function setupTimeago() {
  document.querySelectorAll("time.timeago").forEach((el) => {
    const raw = el.getAttribute("datetime");
    if (raw) {
      el.textContent = timeAgo(raw);
      el.title = raw;
    }
  });
}

/* ── Image preview before upload ─────────────────────────────────── */

function setupImagePreview() {
  const input = document.getElementById("imageInput");
  const preview = document.getElementById("imagePreview");
  if (!input || !preview) return;

  input.addEventListener("change", function () {
    preview.innerHTML = "";
    const files = Array.from(this.files).slice(0, 3);
    files.forEach((file, idx) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const col = document.createElement("div");
        col.className = "col-4 preview-thumb";
        col.innerHTML =
          `<img src="${e.target.result}" alt="Preview ${idx + 1}">` +
          `<button type="button" class="remove-preview" data-idx="${idx}" title="Remove">&times;</button>`;
        preview.appendChild(col);
      };
      reader.readAsDataURL(file);
    });
  });

  preview.addEventListener("click", (e) => {
    const btn = e.target.closest(".remove-preview");
    if (btn) btn.closest(".preview-thumb").remove();
  });
}

/* ── Lightbox ────────────────────────────────────────────────────── */

function setupLightbox() {
  const modalEl = document.getElementById("lightboxModal");
  const modalImg = document.getElementById("lightboxImg");
  if (!modalEl || !modalImg) return;

  const modal = new bootstrap.Modal(modalEl);
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest(".lightbox-trigger");
    if (!trigger) return;
    modalImg.src = trigger.src;
    modalImg.alt = trigger.alt;
    modal.show();
  });
}

/* ── Bootstrap everything on DOM ready ───────────────────────────── */

document.addEventListener("DOMContentLoaded", async () => {
  // 1. Load session and meta in parallel
  const [sessionRes, metaRes] = await Promise.all([
    api("/api/auth/session"),
    api("/api/meta"),
  ]);

  if (sessionRes.ok) state.user = sessionRes.data.user;
  if (metaRes.ok) {
    state.categories = metaRes.data.categories;
    state.places = metaRes.data.places;
  }

  // 2. Render initial UI
  renderNavbar();
  populateSelects();

  // 3. Restore filter selects from URL
  const { cat, place } = getSearchParams();
  if (cat) document.getElementById("filterCategory").value = cat;
  if (place) document.getElementById("filterPlace").value = place;

  // 4. Load posts
  await loadPosts();

  // 5. Setup interactions
  setupSearch();
  setupFilters();
  setupImagePreview();
  setupLightbox();

  // 6. Form handlers
  document.getElementById("loginForm").addEventListener("submit", handleLogin);
  document.getElementById("registerForm").addEventListener("submit", handleRegister);
  document.getElementById("postForm").addEventListener("submit", handlePostSubmit);

  // 7. Clear auth error when modal opens
  document.getElementById("authModal").addEventListener("show.bs.modal", () => {
    document.getElementById("authError").classList.add("d-none");
  });
});
