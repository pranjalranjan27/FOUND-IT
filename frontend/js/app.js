/* ================================================================
   Found IT — app.js
   Fetch-based frontend for a community lost-and-found platform.
   Communicates with Flask REST API. All rendering in JavaScript.
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
  communities: [],
  allPosts: [],
};

/* ── HTML escaping (XSS prevention) ──────────────────────────────── */

function esc(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = String(str);
  return d.innerHTML;
}

/* ── Toast notifications ─────────────────────────────────────────── */

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

/* ── Relative timestamps ─────────────────────────────────────────── */

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

/* ── Category emoji helper ───────────────────────────────────────── */

const EMOJI_MAP = {
  'Mobile':'📱','Laptop':'💻','Charger':'🔌','Book':'📚','ID Card':'🪪',
  'Wallet':'👛','Keys':'🔑','Bag':'🎒','Earphones':'🎧','Power Bank':'🔋',
  'Clothes':'👕'
};

function categoryEmoji(cat) {
  return EMOJI_MAP[cat] || '📦';
}

/* ── Custom dropdown component ───────────────────────────────────── */

class CustomSelect {
  constructor(selectEl) {
    this.select = selectEl;
    this.select.style.display = 'none';

    this.wrapper = document.createElement('div');
    this.wrapper.className = 'custom-dropdown';
    this.select.parentNode.insertBefore(this.wrapper, this.select);
    this.wrapper.appendChild(this.select);

    // Trigger button
    this.trigger = document.createElement('button');
    this.trigger.type = 'button';
    this.trigger.className = 'custom-dropdown-trigger';
    this.trigger.style.cursor = 'pointer';
    this.trigger.innerHTML = `<span class="dd-label dd-placeholder">${this._placeholder()}</span><svg class="dd-chevron" viewBox="0 0 16 16" fill="currentColor"><path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708"/></svg>`;
    this.wrapper.insertBefore(this.trigger, this.select);

    // Menu
    this.menu = document.createElement('div');
    this.menu.className = 'custom-dropdown-menu';
    this.wrapper.appendChild(this.menu);

    this._buildOptions();
    this._bindEvents();
    this._syncLabel();
  }

  _placeholder() {
    const first = this.select.options[0];
    return first && first.value === '' ? first.textContent : 'Select...';
  }

  _buildOptions() {
    this.menu.innerHTML = '';
    Array.from(this.select.options).forEach((opt, i) => {
      const div = document.createElement('div');
      div.className = 'custom-dropdown-option';
      if (opt.value === this.select.value) div.classList.add('active');
      div.textContent = opt.textContent;
      div.dataset.value = opt.value;
      div.dataset.index = i;
      this.menu.appendChild(div);
    });
  }

  _syncLabel() {
    const label = this.trigger.querySelector('.dd-label');
    const selected = this.select.options[this.select.selectedIndex];
    if (selected && selected.value) {
      label.textContent = selected.textContent;
      label.classList.remove('dd-placeholder');
    } else {
      label.textContent = this._placeholder();
      label.classList.add('dd-placeholder');
    }
  }

  _bindEvents() {
    this.trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      // Close other open dropdowns
      document.querySelectorAll('.custom-dropdown.open').forEach(d => {
        if (d !== this.wrapper) d.classList.remove('open');
      });
      this.wrapper.classList.toggle('open');
    });

    this.menu.addEventListener('click', (e) => {
      const opt = e.target.closest('.custom-dropdown-option');
      if (!opt) return;
      this.select.value = opt.dataset.value;
      this.select.dispatchEvent(new Event('change', { bubbles: true }));
      this.menu.querySelectorAll('.custom-dropdown-option').forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      this._syncLabel();
      this.wrapper.classList.remove('open');
    });

    document.addEventListener('click', () => this.wrapper.classList.remove('open'));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.wrapper.classList.remove('open');
    });
  }

  refresh() {
    this._buildOptions();
    this._syncLabel();
  }

  setValue(val) {
    this.select.value = val;
    this._buildOptions();
    this._syncLabel();
  }
}

const customSelects = {};

function initCustomSelects() {
  ['communitySelect', 'filterCategory', 'filterPlace', 'postCommunity', 'postCategory', 'postPlace'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !customSelects[id]) {
      customSelects[id] = new CustomSelect(el);
    }
  });
}

function refreshCustomSelects() {
  Object.values(customSelects).forEach(cs => cs.refresh());
}

/* ── Card rendering ──────────────────────────────────────────────── */

function renderCard(p) {
  const isOwner = state.user && p.user_id === state.user.id;

  let cardClasses = "card";
  if (p.status === "closed") cardClasses += " card-closed";
  if (isOwner) cardClasses += " card-own";

  // Kind tag overlay
  const kindTag = `<span class="card-kind-tag ${p.kind}">${p.kind === "found" ? "Found" : "Lost"}</span>`;

  // Hero image
  let heroHtml = "";
  if (p.images && p.images.length) {
    heroHtml = `
      <div class="card-img-top-container">
        ${kindTag}
        <img class="card-img-top"
             src="/uploads/${esc(p.images[0])}"
             alt="Photo of ${esc(p.item_name)}"
             loading="lazy">
      </div>`;
  } else {
    heroHtml = `
      <div class="card-img-top-container">
        ${kindTag}
        <div class="card-img-placeholder">${categoryEmoji(p.category)}</div>
      </div>`;
  }

  // Chips
  let chipsHtml = `<div class="card-chips">
    <span class="chip chip-category">${esc(p.category || "Other")}</span>
    ${p.community ? `<span class="chip chip-community">${esc(p.community)}</span>` : ""}
  </div>`;

  // Meta row
  let metaHtml = `<div class="card-meta">
    <svg viewBox="0 0 16 16" fill="currentColor"><path d="M12.166 8.94c-.524 1.062-1.234 2.12-1.96 3.07A32 32 0 0 1 8 14.58a32 32 0 0 1-2.206-2.57c-.726-.95-1.436-2.008-1.96-3.07C3.304 7.867 3 6.862 3 6a5 5 0 0 1 10 0c0 .862-.305 1.867-.834 2.94M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10"/><path d="M8 8a2 2 0 1 1 0-4 2 2 0 0 1 0 4m0 1a3 3 0 1 0 0-6 3 3 0 0 0 0 6"/></svg>
    <span>${esc(p.place || "Other")}</span>
    <span class="meta-dot"></span>
    <time class="timeago" datetime="${esc(p.created_at)}">${esc(p.created_at)}</time>
  </div>`;

  return `
    <div class="${cardClasses}" data-post-id="${p.id}">
      ${heroHtml}
      <div class="card-body">
        ${chipsHtml}
        <div class="card-title">${esc(p.item_name)}</div>
        ${metaHtml}
      </div>
    </div>`;
}

function renderEmptyState(kind) {
  if (kind === "found") {
    return `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">📦</div>
        <h5>No found items posted yet</h5>
        <p>Found something in your community? Post it here to help reunite it with its owner.</p>
        <button class="btn btn-outline-success btn-sm" onclick="openPostModal('found')">Post a found item</button>
      </div>`;
  }
  return `
    <div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">🔍</div>
      <h5>No lost items reported</h5>
      <p>Lost something? Post the details and someone in your community might have found it.</p>
      <button class="btn btn-outline-danger btn-sm" onclick="openPostModal('lost')">Report a lost item</button>
    </div>`;
}

/* ── Item detail modal ───────────────────────────────────────────── */

function openItemDetail(postId) {
  const post = state.allPosts.find(p => p.id === postId);
  if (!post) return;

  const isOwner = state.user && post.user_id === state.user.id;
  const p = post;

  // Hero image
  let heroHtml = "";
  if (p.images && p.images.length) {
    heroHtml = `<img class="detail-hero lightbox-trigger" src="/uploads/${esc(p.images[0])}" alt="${esc(p.item_name)}">`;
  } else {
    heroHtml = `<div class="detail-hero-placeholder">${categoryEmoji(p.category)}</div>`;
  }

  // Extra images thumbnails
  let thumbsHtml = "";
  if (p.images && p.images.length > 1) {
    const thumbs = p.images.map((img, i) => `
      <img class="lightbox-trigger${i === 0 ? ' active' : ''}"
           src="/uploads/${esc(img)}" alt="Photo ${i+1}"
           onclick="document.querySelector('.detail-hero').src=this.src">`
    ).join("");
    thumbsHtml = `<div class="detail-images-row">${thumbs}</div>`;
  }

  // Contact section
  let contactHtml = "";
  if (p.name) {
    const initial = p.name.charAt(0).toUpperCase();
    contactHtml = `
      <div class="detail-contact">
        <div class="detail-contact-avatar">${esc(initial)}</div>
        <div class="detail-contact-info">
          <div class="detail-contact-name">${esc(p.name)}</div>
          ${p.phone ? `<div class="detail-contact-phone"><a href="tel:${esc(p.phone)}">${esc(p.phone)}</a></div>` : '<div style="font-size:.82rem;color:var(--muted)">No phone provided</div>'}
        </div>
      </div>`;
  }

  // Status badge
  let statusBadge = "";
  if (p.status === "claim_requested") {
    statusBadge = `<span class="claim-status claim-status-pending">⏳ Claim Pending${p.claim_count > 0 ? ` (${p.claim_count})` : ''}</span>`;
  } else if (p.status === "closed") {
    statusBadge = `<span class="claim-status claim-status-approved">✅ Closed</span>`;
  }

  // Owner actions
  let ownerHtml = "";
  if (isOwner) {
    if (p.status === "closed") {
      ownerHtml = `
        <div class="detail-owner-actions">
          <span class="claim-status claim-status-approved">✅ Closed</span>
        </div>`;
    } else {
      let ownerBtns = '';
      if (p.claim_count > 0) {
        ownerBtns += `<button class="btn btn-primary btn-sm" onclick="openClaimsReview(); bootstrap.Modal.getInstance(document.getElementById('itemDetailModal')).hide();">📋 Review Claims (${p.claim_count})</button>`;
      }
      ownerBtns += `<button class="btn btn-outline-secondary btn-sm" onclick="handleClosePost(${p.id}); bootstrap.Modal.getInstance(document.getElementById('itemDetailModal')).hide();">Close Post</button>`;
      ownerHtml = `<div class="detail-owner-actions">${ownerBtns}</div>`;
    }
  }

  // Claim button — only for signed-in non-owners on non-closed items
  let claimHtml = "";
  if (state.user && !isOwner && p.status !== "closed") {
    const btnLabel = p.kind === "found" ? "🤚 Claim This Item" : "📦 I Found Your Item";
    const btnSubtitle = p.kind === "found"
      ? "Submit proof that this belongs to you"
      : "Provide proof that you found this item";
    claimHtml = `
      <div class="detail-owner-actions">
        <button class="btn btn-primary btn-sm" onclick="openClaimModal(${p.id}, '${esc(p.item_name).replace(/'/g, "\\'")}', '${p.kind}')">${btnLabel}</button>
        <span style="font-size:.72rem;color:var(--muted)">${btnSubtitle}</span>
      </div>`;
  } else if (p.status === "closed" && !isOwner) {
    claimHtml = `
      <div class="detail-owner-actions">
        ${statusBadge}
      </div>`;
  }

  const bodyHtml = `
    ${heroHtml}
    ${thumbsHtml}
    <div class="detail-content">
      <span class="detail-kind-tag ${p.kind}">${p.kind === "found" ? "📦 Found Item" : "🔍 Lost Item"}</span>
      ${statusBadge ? `<div style="margin-top:8px">${statusBadge}</div>` : ''}
      <h3 class="detail-title">${esc(p.item_name)}</h3>

      <div class="detail-grid">
        <div class="detail-field">
          <span class="detail-field-label">Category</span>
          <span class="detail-field-value">${categoryEmoji(p.category)} ${esc(p.category || "Other")}</span>
        </div>
        <div class="detail-field">
          <span class="detail-field-label">Location</span>
          <span class="detail-field-value">📍 ${esc(p.place || "Other")}</span>
        </div>
        <div class="detail-field">
          <span class="detail-field-label">Community</span>
          <span class="detail-field-value">${esc(p.community || "Not specified")}</span>
        </div>
        <div class="detail-field">
          <span class="detail-field-label">Posted</span>
          <span class="detail-field-value">${timeAgo(p.created_at)}</span>
        </div>
      </div>

      ${p.description ? `<div class="detail-description">${esc(p.description)}</div>` : ""}

      <div style="font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Posted by</div>
      ${contactHtml}
    </div>
    ${ownerHtml}
    ${claimHtml}`;

  document.getElementById("detailModalBody").innerHTML = bodyHtml;
  document.getElementById("detailModalTitle").textContent = p.item_name;

  new bootstrap.Modal(document.getElementById("itemDetailModal")).show();
}

/* ── Navbar rendering ────────────────────────────────────────────── */

function renderNavbar() {
  const nav = document.getElementById("navAuth");
  if (state.user) {
    const initial = (state.user.name || state.user.email || "U").charAt(0).toUpperCase();
    nav.innerHTML = `
      <div class="user-dropdown">
        <div class="user-dropdown-toggle" id="userDropdownToggle">
          <div class="user-avatar">${esc(initial)}</div>
          <span class="user-name d-none d-md-inline">${esc(state.user.name || state.user.email)}</span>
          <svg viewBox="0 0 16 16" fill="currentColor"><path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708"/></svg>
        </div>
        <div class="user-dropdown-menu" id="userDropdownMenu">
          <div class="user-dropdown-header">
            <div style="font-weight:600;color:var(--text)">${esc(state.user.name || 'User')}</div>
            <div style="font-size:.76rem;color:var(--muted);margin-top:2px">${esc(state.user.email || '')}</div>
          </div>
          <button class="user-dropdown-item" id="myPostsBtn">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><path d="M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2zm15 0a1 1 0 0 0-1-1H2a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1zM3 4h10v1H3zm0 3h10v1H3zm0 3h7v1H3z"/></svg>
            My Posts
          </button>
          <button class="user-dropdown-item" id="myRequestsBtn">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><path d="M2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2zm6.5 4.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3a.5.5 0 0 1 1 0"/></svg>
            Requests
          </button>
          <button class="user-dropdown-item" id="myActivityBtn">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><path d="M8.515 1.019A7 7 0 0 0 8 1V0a8 8 0 0 1 .589.022l-.074.997M5.205.33a7 7 0 0 0-.832.28l.36.943a6 6 0 0 1 .71-.24zM3.18 1.394a7 7 0 0 0-.725.484l.58.81a6 6 0 0 1 .619-.414l-.474-.88M1.394 3.18a7 7 0 0 0-.484.725l.81.58a6 6 0 0 1 .414-.619l-.74-.686M.33 5.205a7 7 0 0 0-.28.832l.943.36a6 6 0 0 1 .24-.71l-.903-.482M.019 7.485A7 7 0 0 0 0 8a8 8 0 0 0 16 0 7 7 0 0 0-.019-.515l-.997.074A6 6 0 0 1 1.019 8.515l-.997-.074zM8 4a.5.5 0 0 1 .5.5v3.793l2.354 2.353a.5.5 0 0 1-.708.708L7.854 9.061a.5.5 0 0 1-.154-.36V4.5A.5.5 0 0 1 8 4"/></svg>
            Activity
          </button>
          <div class="user-dropdown-divider"></div>
          <button class="user-dropdown-item text-danger" id="logoutBtn">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><path fill-rule="evenodd" d="M10 12.5a.5.5 0 0 1-.5.5h-8a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5h8a.5.5 0 0 1 .5.5v2a.5.5 0 0 0 1 0v-2A1.5 1.5 0 0 0 9.5 2h-8A1.5 1.5 0 0 0 0 3.5v9A1.5 1.5 0 0 0 1.5 14h8a1.5 1.5 0 0 0 1.5-1.5v-2a.5.5 0 0 0-1 0z"/><path fill-rule="evenodd" d="M15.854 8.354a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L14.293 7.5H5.5a.5.5 0 0 0 0 1h8.793l-2.147 2.146a.5.5 0 0 0 .708.708z"/></svg>
            Logout
          </button>
        </div>
      </div>`;

    // Toggle dropdown
    const toggle = document.getElementById("userDropdownToggle");
    const menu = document.getElementById("userDropdownMenu");
    toggle.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.toggle("show");
    });
    document.addEventListener("click", () => menu.classList.remove("show"));

    document.getElementById("myPostsBtn").addEventListener("click", () => {
      menu.classList.remove("show");
      openMyPosts();
    });
    document.getElementById("myRequestsBtn").addEventListener("click", () => {
      menu.classList.remove("show");
      openRequestsReview();
    });
    document.getElementById("myActivityBtn").addEventListener("click", () => {
      menu.classList.remove("show");
      openActivityPage();
    });
    document.getElementById("logoutBtn").addEventListener("click", handleLogout);
  } else {
    nav.innerHTML = `<button class="btn btn-primary btn-sm" id="openLogin">Sign In</button>`;
    document.getElementById("openLogin").addEventListener("click", () => {
      new bootstrap.Modal(document.getElementById("authModal")).show();
    });
  }
}

/* ── My Posts dashboard ───────────────────────────────────────── */

async function openMyPosts() {
  const modal = new bootstrap.Modal(document.getElementById("myPostsModal"));
  const listEl = document.getElementById("myPostsList");
  const actEl = document.getElementById("activityLog");

  listEl.innerHTML = '<div class="text-center p-4"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';
  actEl.innerHTML = '';
  modal.show();

  const res = await api("/api/posts/mine");
  if (!res.ok) {
    listEl.innerHTML = '<div class="my-posts-empty"><p>Could not load posts.</p></div>';
    return;
  }

  const posts = res.data.posts;
  if (!posts.length) {
    listEl.innerHTML = `
      <div class="my-posts-empty">
        <div class="empty-icon">📫</div>
        <h5>No posts yet</h5>
        <p>Your found and lost item posts will appear here.</p>
      </div>`;
    actEl.innerHTML = `
      <div class="my-posts-empty">
        <div class="empty-icon">💭</div>
        <h5>No activity yet</h5>
        <p>Your activity timeline will appear here once you start posting.</p>
      </div>`;
    return;
  }

  const foundPosts = posts.filter(p => p.kind === "found");
  const lostPosts = posts.filter(p => p.kind === "lost");

  listEl.innerHTML = renderMyPostsSection("Found Items", foundPosts, "📦") +
                     renderMyPostsSection("Lost Items", lostPosts, "🔍");

  actEl.innerHTML = renderActivityLog(posts);

  // Attach status change listeners
  listEl.querySelectorAll("[data-status-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const postId = btn.getAttribute("data-post-id");
      const newStatus = btn.getAttribute("data-status-action");
      await handleStatusChange(postId, newStatus);
    });
  });
}

function renderMyPostsSection(title, posts, emoji) {
  if (!posts.length) return '';
  const rows = posts.map(p => renderMyPostRow(p)).join('');
  return `<div class="mb-3">
    <div style="font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${emoji} ${esc(title)} (${posts.length})</div>
    ${rows}
  </div>`;
}

function renderMyPostRow(p) {
  let thumb = '';
  if (p.images && p.images.length) {
    thumb = `<img class="my-post-thumb" src="/uploads/${esc(p.images[0])}" alt="${esc(p.item_name)}">`;
  } else {
    thumb = `<div class="my-post-thumb-placeholder">${categoryEmoji(p.category)}</div>`;
  }

  const statusLabels = { 'active': 'Active', 'claim_requested': 'Claim Pending', 'closed': 'Closed' };
  const statusLabel = statusLabels[p.status] || p.status;
  const statusBadge = `<span class="status-badge status-${esc(p.status)}">${esc(statusLabel)}</span>`;

  let actions = '';
  if (p.status === 'active' || p.status === 'claim_requested') {
    if (p.claim_count > 0) {
      actions += `<button class="btn-status" onclick="openClaimsReview()">📋 Review (${p.claim_count})</button>`;
    }
    actions += `<button class="btn-status" onclick="handleClosePost(${p.id})">Close</button>`;
  }

  return `
    <div class="my-post-row">
      ${thumb}
      <div class="my-post-info">
        <div class="my-post-title">${esc(p.item_name)}</div>
        <div class="my-post-meta">
          ${statusBadge}
          <span>·</span>
          <span>${esc(p.community || 'No community')}</span>
          <span>·</span>
          <span>${timeAgo(p.created_at)}</span>
        </div>
      </div>
      <div class="my-post-actions">${actions}</div>
    </div>`;
}

function renderActivityLog(posts) {
  const activities = posts.map(p => {
    const entries = [];
    entries.push({
      type: p.kind,
      icon: p.kind === 'found' ? '📦' : '🔍',
      iconClass: p.kind === 'found' ? 'activity-icon-found' : 'activity-icon-lost',
      title: `Posted ${p.kind} item: <strong>${esc(p.item_name)}</strong>`,
      time: p.created_at,
    });
    if (p.status === 'claim_requested') {
      entries.push({ type:'status', icon:'📩', iconClass:'activity-icon-status',
        title:`<strong>${esc(p.item_name)}</strong> has pending claims`, time:p.created_at });
    } else if (p.status === 'closed') {
      entries.push({ type:'status', icon:'✅', iconClass:'activity-icon-status',
        title:`<strong>${esc(p.item_name)}</strong> closed`, time:p.created_at });
    }
    return entries;
  }).flat();

  activities.sort((a, b) => new Date(b.time) - new Date(a.time));

  if (!activities.length) {
    return `<div class="my-posts-empty"><div class="empty-icon">💭</div><h5>No activity</h5></div>`;
  }

  return activities.map(a => `
    <div class="activity-row">
      <div class="activity-icon ${a.iconClass}">${a.icon}</div>
      <div class="activity-content">
        <div class="activity-title">${a.title}</div>
        <div class="activity-time">${timeAgo(a.time)}</div>
      </div>
      <div class="activity-arrow">
        <svg viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708"/></svg>
      </div>
    </div>`
  ).join('');
}

async function handleStatusChange(postId, newStatus) {
  const res = await api(`/api/posts/${postId}/status`, { json: { status: newStatus } });
  if (res.ok) {
    showToast(`Post marked as ${newStatus}.`, "success");
    openMyPosts();
    loadPosts();
  } else {
    showToast(res.error || "Could not update status.", "error");
  }
}

/* ── Populate select dropdowns from meta ─────────────────────────── */

function populateSelects() {
  // Categories
  ["filterCategory", "postCategory"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    while (sel.options.length > (id.startsWith("filter") ? 1 : 0))
      sel.remove(sel.options.length - 1);
    state.categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      sel.appendChild(opt);
    });
  });

  // Places
  ["filterPlace", "postPlace"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    while (sel.options.length > (id.startsWith("filter") ? 1 : 0))
      sel.remove(sel.options.length - 1);
    state.places.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p; opt.textContent = p;
      sel.appendChild(opt);
    });
  });

  // Communities
  ["communitySelect", "postCommunity"].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    while (sel.options.length > (id === "communitySelect" ? 1 : 0))
      sel.remove(sel.options.length - 1);
    state.communities.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      sel.appendChild(opt);
    });
  });

  // Refresh custom dropdowns after options change
  refreshCustomSelects();
}

/* ── URL state management (history.pushState) ────────────────────── */

function getSearchParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    cat: params.get("cat") || "",
    place: params.get("place") || "",
    community: params.get("community") || "",
  };
}

function setSearchParams(q, cat, place, community) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (cat) params.set("cat", cat);
  if (place) params.set("place", place);
  if (community) params.set("community", community);
  const qs = params.toString();
  const newUrl = qs ? `?${qs}` : window.location.pathname;
  history.pushState({}, "", newUrl);
}

/* ── Data loading ────────────────────────────────────────────────── */

async function loadPosts() {
  const { q, cat, place, community } = getSearchParams();
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (cat) params.set("cat", cat);
  if (place) params.set("place", place);
  if (community) params.set("community", community);

  const qs = params.toString();

  const [foundRes, lostRes] = await Promise.all([
    api(`/api/posts?kind=found${qs ? "&" + qs : ""}`),
    api(`/api/posts?kind=lost${qs ? "&" + qs : ""}`),
  ]);

  const foundPosts = foundRes.ok ? foundRes.data.posts : [];
  const lostPosts = lostRes.ok ? lostRes.data.posts : [];

  // Store all posts for detail modal lookups
  state.allPosts = [...foundPosts, ...lostPosts];

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

  // Post-render hooks
  setupTimeago();
}

/* ── Auth handlers ───────────────────────────────────────────────── */

function resetAuthForms() {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  if (loginForm) loginForm.reset();
  if (registerForm) registerForm.reset();
  const err = document.getElementById('authError');
  if (err) err.classList.add('d-none');
}

async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const email = form.email.value.trim();
  const password = form.password.value;

  const res = await api("/api/auth/login", { json: { email, password } });

  if (res.ok) {
    state.user = res.data.user;
    resetAuthForms();
    bootstrap.Modal.getInstance(document.getElementById("authModal"))?.hide();
    renderNavbar();
    showToast("Signed in successfully.", "success");
    loadPosts();
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
    phone: form.phone.value.trim(),
    password: form.password.value,
  };

  const res = await api("/api/auth/register", { json: body });

  if (res.ok) {
    state.user = res.data.user;
    resetAuthForms();
    bootstrap.Modal.getInstance(document.getElementById("authModal"))?.hide();
    renderNavbar();
    showToast("Account created. Welcome!", "success");
    loadPosts();
    prefillPostForm();
  } else {
    const err = document.getElementById("authError");
    err.textContent = res.error || "Registration failed.";
    err.classList.remove("d-none");
  }
}

async function handleLogout() {
  await Promise.all([
    api("/auth/logout", { method: "POST" }),
    api("/api/auth/logout", { method: "POST" }),
  ]);
  state.user = null;
  resetAuthForms();
  renderNavbar();
  showToast("Signed out.", "success");
  loadPosts();
}

/* ── Post creation ───────────────────────────────────────────────── */

function prefillPostForm() {
  if (!state.user) return;
  const u = state.user;
  const name = document.getElementById("postName");
  const phone = document.getElementById("postPhone");
  if (name && !name.value) name.value = u.name || "";
  if (phone && !phone.value) phone.value = u.phone || "";
}

function openPostModal(kind) {
  if (!state.user) {
    const err = document.getElementById("authError");
    if (err) {
      err.textContent = "You need to sign in first.";
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
    ? "Post a found item" : "Report a lost item";
  document.getElementById("postKind").value = kind;

  // Pre-select community from search filter if set
  const currentCommunity = document.getElementById("communitySelect").value;
  if (currentCommunity) {
    document.getElementById("postCommunity").value = currentCommunity;
  }

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
      showToast("Posted successfully!", "success");
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

/* ── Post close (owner) ──────────────────────────────────────────── */

async function handleClosePost(postId) {
  if (!confirm("Close this post? All pending claims will be rejected.")) return;

  const res = await api(`/api/posts/${postId}/close`, { method: "POST" });
  if (res.ok) {
    showToast("Post closed successfully.", "success");
    loadPosts();
  } else {
    showToast(res.error || "Could not close post.", "error");
  }
}
window.handleClosePost = handleClosePost;

/* ── Search & filters ────────────────────────────────────────────── */

function setupSearch() {
  const input = document.getElementById("searchInput");
  const btn = document.getElementById("searchBtn");
  const hiddenCat = document.getElementById("hiddenCat");
  const hiddenPlace = document.getElementById("hiddenPlace");
  const communitySelect = document.getElementById("communitySelect");

  const { q, cat, place, community } = getSearchParams();
  if (q) input.value = q;
  if (cat) hiddenCat.value = cat;
  if (place) hiddenPlace.value = place;
  if (community) communitySelect.value = community;

  function doSearch() {
    const query = input.value.trim();
    const category = hiddenCat.value;
    const placeVal = hiddenPlace.value;
    const comm = communitySelect.value;
    setSearchParams(query, category, placeVal, comm);
    loadPosts();
  }

  btn.addEventListener("click", doSearch);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  communitySelect.addEventListener("change", doSearch);

  window.addEventListener("popstate", () => {
    const p = getSearchParams();
    input.value = p.q;
    hiddenCat.value = p.cat;
    hiddenPlace.value = p.place;
    communitySelect.value = p.community;
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
    if (customSelects.filterCategory) customSelects.filterCategory.refresh();
    if (customSelects.filterPlace) customSelects.filterPlace.refresh();
    modal.show();
  });

  document.getElementById("filtersClear").addEventListener("click", () => {
    hiddenCat.value = "";
    hiddenPlace.value = "";
    selCat.value = "";
    selPlace.value = "";
    if (customSelects.filterCategory) customSelects.filterCategory.refresh();
    if (customSelects.filterPlace) customSelects.filterPlace.refresh();
  });

  document.getElementById("filtersApply").addEventListener("click", () => {
    hiddenCat.value = selCat.value || "";
    hiddenPlace.value = selPlace.value || "";
    modal.hide();
    const query = document.getElementById("searchInput").value.trim();
    const comm = document.getElementById("communitySelect").value;
    setSearchParams(query, hiddenCat.value, hiddenPlace.value, comm);
    loadPosts();
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
    e.stopPropagation();
    modalImg.src = trigger.src;
    modalImg.alt = trigger.alt;
    modal.show();
  });
}

/* ── Card click → detail modal (delegated) ───────────────────────── */

function setupCardClicks() {
  document.addEventListener("click", (e) => {
    // Don't open detail modal if clicking a button, link, lightbox trigger, etc.
    if (e.target.closest("button, a, .lightbox-trigger, .remove-preview")) return;

    const card = e.target.closest(".card[data-post-id]");
    if (!card) return;

    const postId = parseInt(card.getAttribute("data-post-id"), 10);
    if (postId) openItemDetail(postId);
  });
}

/* ── Mobile FAB ──────────────────────────────────────────────────── */

function setupMobileFab() {
  const fab = document.getElementById("mobileFab");
  if (!fab) return;

  fab.addEventListener("click", () => {
    const lostTab = document.getElementById("lost-tab");
    const isLostActive = lostTab && lostTab.classList.contains("active");
    openPostModal(isLostActive ? "lost" : "found");
  });
}

/* ── Claim workflow ──────────────────────────────────────────────── */

function openClaimModal(postId, itemName, postKind) {
  // Close the detail modal first
  const detailModal = bootstrap.Modal.getInstance(document.getElementById('itemDetailModal'));
  if (detailModal) detailModal.hide();

  document.getElementById('claimPostId').value = postId;
  document.getElementById('claimItemName').textContent = itemName;
  document.getElementById('claimForm').reset();

  // Set dynamic title, prompt, placeholder, and proof label based on post kind
  const titleEl = document.getElementById('claimModalTitle');
  const promptEl = document.getElementById('claimPromptLabel');
  const messageEl = document.getElementById('claimMessage');
  const proofLabel = document.getElementById('claimProofLabel');
  const proofHint = document.getElementById('claimProofHint');
  if (postKind === 'lost') {
    if (titleEl) titleEl.textContent = 'I Have Your Item';
    if (promptEl) promptEl.textContent = 'Describe the item';
    if (messageEl) messageEl.placeholder = 'Describe identifying features and where/how you found the item...';
    if (proofLabel) proofLabel.textContent = 'Supporting files (photos of the item, up to 3)';
    if (proofHint) proofHint.textContent = 'e.g. photos of the item, location where found';
  } else {
    if (titleEl) titleEl.textContent = 'Claim This Item';
    if (promptEl) promptEl.textContent = 'Why does this item belong to you?';
    if (messageEl) messageEl.placeholder = 'Describe identifying features, when/where you lost it, or any proof of ownership\u2026';
    if (proofLabel) proofLabel.textContent = 'Proof files (images or PDF, up to 3)';
    if (proofHint) proofHint.textContent = 'e.g. purchase receipt, warranty card, ownership photos';
  }

  // Pre-fill with user info
  if (state.user) {
    const nameEl = document.getElementById('claimName');
    const emailEl = document.getElementById('claimEmail');
    if (nameEl && !nameEl.value) nameEl.value = state.user.name || '';
    if (emailEl && !emailEl.value) emailEl.value = state.user.email || '';
  }

  setTimeout(() => {
    new bootstrap.Modal(document.getElementById('claimModal')).show();
  }, 300);
}
window.openClaimModal = openClaimModal;

async function handleClaimSubmit(e) {
  e.preventDefault();

  const postId = document.getElementById('claimPostId').value;
  const formData = new FormData(document.getElementById('claimForm'));

  const btnText = document.querySelector('#claimSubmitBtn .btn-text');
  const spinner = document.getElementById('claimSpinner');
  if (btnText) btnText.textContent = 'Submitting…';
  if (spinner) spinner.classList.remove('d-none');

  try {
    const res = await fetch(`/api/posts/${postId}/claim`, {
      method: 'POST',
      credentials: 'same-origin',
      body: formData,
    });
    const data = await res.json();

    if (data.ok) {
      bootstrap.Modal.getInstance(document.getElementById('claimModal'))?.hide();
      showToast('Claim submitted! The poster will review your request.', 'success');
    } else {
      showToast(data.error || 'Could not submit claim.', 'error');
    }
  } catch (err) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    if (btnText) btnText.textContent = 'Submit Claim';
    if (spinner) spinner.classList.add('d-none');
  }
}

async function openRequestsReview() {
  const claimList = document.getElementById('reqClaimList');
  const returnList = document.getElementById('reqReturnList');
  claimList.innerHTML = '<div class="text-center p-4"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';
  returnList.innerHTML = '';

  new bootstrap.Modal(document.getElementById('requestsReviewModal')).show();

  const res = await api('/api/claims/mine');
  if (!res.ok) {
    claimList.innerHTML = '<div class="my-posts-empty"><p>Could not load requests.</p></div>';
    return;
  }

  const claims = res.data.claims;
  const claimReqs = claims.filter(c => (c.request_type || 'claim') === 'claim');
  const returnReqs = claims.filter(c => c.request_type === 'return');

  claimList.innerHTML = claimReqs.length
    ? claimReqs.map(c => renderRequestCard(c)).join('')
    : `<div class="my-posts-empty"><div class="empty-icon">📫</div><h5>No claim requests</h5><p>When someone claims your found item, it will appear here.</p></div>`;

  returnList.innerHTML = returnReqs.length
    ? returnReqs.map(c => renderRequestCard(c)).join('')
    : `<div class="my-posts-empty"><div class="empty-icon">📫</div><h5>No return requests</h5><p>When someone says they have your lost item, it will appear here.</p></div>`;
}
// Keep backward compat — old inline onclicks may reference openClaimsReview
function openClaimsReview() { openRequestsReview(); }

function renderRequestCard(c) {
  const proofHtml = c.files.length ? `
    <div class="claim-proof-row">
      ${c.files.map(f => {
        const isPdf = f.original_name && f.original_name.toLowerCase().endsWith('.pdf');
        const icon = isPdf
          ? '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/></svg>'
          : '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0"/><path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1z"/></svg>';
        return `<a href="/uploads/${esc(f.filename)}" target="_blank" class="claim-proof-item">${icon} ${esc(f.original_name || f.filename)}</a>`;
      }).join('')}
    </div>` : '';

  const typeLabel = (c.request_type || 'claim') === 'return' ? 'Return Request' : 'Claim Request';

  let actionsHtml = '';
  if (c.status === 'pending') {
    actionsHtml = `
      <div class="claim-actions">
        <button class="btn btn-primary btn-sm" onclick="handleClaimAction(${c.id}, 'approve')">Approve</button>
        <button class="btn btn-outline-danger btn-sm" onclick="handleClaimAction(${c.id}, 'reject')">Reject</button>
      </div>`;
  }

  return `
    <div class="claim-card">
      <div class="claim-card-header">
        <div>
          <div class="claim-card-item">${categoryEmoji(c.item_category)} ${esc(c.item_name)}</div>
          <div class="claim-card-time">${typeLabel} · ${timeAgo(c.created_at)}</div>
        </div>
        <span class="claim-status claim-status-${esc(c.status)}">${esc(c.status)}</span>
      </div>
      <div class="claim-info-row">
        <span><strong>From:</strong> ${esc(c.claimant_name)}</span>
        <span><strong>Email:</strong> ${esc(c.claimant_email)}</span>
        ${c.claimant_phone ? `<span><strong>Phone:</strong> ${esc(c.claimant_phone)}</span>` : ''}
      </div>
      ${c.message ? `<div class="claim-message">${esc(c.message)}</div>` : ''}
      ${proofHtml}
      ${actionsHtml}
    </div>`;
}

async function handleClaimAction(claimId, action) {
  const confirmMsg = action === 'approve'
    ? 'Approve this request? The post will be closed and all other pending requests will be rejected.'
    : 'Reject this request?';
  if (!confirm(confirmMsg)) return;

  const res = await api(`/api/claims/${claimId}/${action}`, { method: 'POST' });
  if (res.ok) {
    const msg = action === 'approve'
      ? 'Request approved! Post closed.'
      : 'Request rejected.';
    showToast(msg, 'success');
    openRequestsReview();
    loadPosts();
  } else {
    showToast(res.error || `Could not ${action} request.`, 'error');
  }
}
window.handleClaimAction = handleClaimAction;

/* ── Activity page ──────────────────────────────────────────────── */

const activityIcons = {
  claim_submitted: '📩',
  claim_received: '📬',
  claim_approved: '✅',
  claim_approved_claimant: '✅',
  claim_rejected: '❌',
  claim_rejected_claimant: '❌',
  return_submitted: '📦',
  return_received: '📬',
  return_approved: '✅',
  return_approved_claimant: '✅',
  return_rejected: '❌',
  return_rejected_claimant: '❌',
  item_created_found: '📦',
  item_created_lost: '🔍',
  contact_requested: '📞',
  contact_received: '📞',
  contact_shared: '📱',
  contact_shared_to: '📱',
};

async function openActivityPage(filter) {
  const bodyEl = document.getElementById('activityFeedBody');
  const filterEl = document.getElementById('activityFilter');
  bodyEl.innerHTML = '<div class="text-center p-4"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';

  const modal = bootstrap.Modal.getInstance(document.getElementById('activityModal'))
    || new bootstrap.Modal(document.getElementById('activityModal'));
  modal.show();

  const filt = filter || filterEl.value || 'all';
  filterEl.value = filt;

  const res = await api(`/api/activity?filter=${encodeURIComponent(filt)}`);
  if (!res.ok) {
    bodyEl.innerHTML = '<div class="my-posts-empty"><p>Could not load activity.</p></div>';
    return;
  }

  const activities = res.data.activities;
  if (!activities.length) {
    bodyEl.innerHTML = `
      <div class="my-posts-empty">
        <div class="empty-icon">💭</div>
        <h5>No activity yet</h5>
        <p>Your activity timeline will appear here as you use Found IT.</p>
      </div>`;
    return;
  }

  bodyEl.innerHTML = activities.map(a => {
    const icon = activityIcons[a.event_type] || '📌';
    return `
      <div class="activity-row">
        <div class="activity-icon activity-icon-status">${icon}</div>
        <div class="activity-content">
          <div class="activity-title">${a.message}</div>
          <div class="activity-time">${timeAgo(a.created_at)}</div>
        </div>
      </div>`;
  }).join('');

  // Attach filter change
  filterEl.onchange = () => openActivityPage(filterEl.value);
}
window.openActivityPage = openActivityPage;

/* ── Bootstrap everything on DOM ready ───────────────────────────── */

document.addEventListener("DOMContentLoaded", async () => {
  // 1. Load meta data
  const metaRes = await api("/api/meta");
  if (metaRes.ok) {
    state.categories = metaRes.data.categories;
    state.places = metaRes.data.places;
    state.communities = metaRes.data.communities;
  }

  // 2. Detect auth — check Google OAuth first, then fall back to dev session
  const googleRes = await api("/auth/user");
  if (googleRes.authenticated && googleRes.user) {
    state.user = googleRes.user;
  } else {
    const sessionRes = await api("/api/auth/session");
    if (sessionRes.ok && sessionRes.data.user) {
      state.user = sessionRes.data.user;
    }
  }

  // 3. Render initial UI
  renderNavbar();
  populateSelects();

  // 4. Initialize custom dropdowns (after options are populated)
  initCustomSelects();

  // 5. Restore filters from URL
  const { cat, place, community } = getSearchParams();
  if (cat) {
    document.getElementById("filterCategory").value = cat;
    if (customSelects.filterCategory) customSelects.filterCategory.refresh();
  }
  if (place) {
    document.getElementById("filterPlace").value = place;
    if (customSelects.filterPlace) customSelects.filterPlace.refresh();
  }
  if (community) {
    document.getElementById("communitySelect").value = community;
    if (customSelects.communitySelect) customSelects.communitySelect.refresh();
  }

  // 6. Load posts
  await loadPosts();

  // 7. Setup interactions
  setupSearch();
  setupFilters();
  setupImagePreview();
  setupLightbox();
  setupCardClicks();
  setupMobileFab();

  // 8. Form handlers
  document.getElementById("loginForm").addEventListener("submit", handleLogin);
  document.getElementById("registerForm").addEventListener("submit", handleRegister);
  document.getElementById("postForm").addEventListener("submit", handlePostSubmit);
  document.getElementById("claimForm").addEventListener("submit", handleClaimSubmit);

  // 9. Reset auth forms on modal open, close, and tab switch
  const authModalEl = document.getElementById("authModal");
  authModalEl.addEventListener("show.bs.modal", () => {
    resetAuthForms();
  });
  authModalEl.addEventListener("hidden.bs.modal", () => {
    resetAuthForms();
  });
  document.querySelectorAll('#authTabs button[data-bs-toggle="tab"]').forEach(tab => {
    tab.addEventListener('shown.bs.tab', () => {
      resetAuthForms();
    });
  });
});
