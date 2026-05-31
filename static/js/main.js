/* ================================================================
   Found IT — main.js
   All existing behaviour preserved; new features layered on top.
   ================================================================ */

/* ── Auth helpers ─────────────────────────────────────────────── */

function isLoggedIn() {
  return document.body.getAttribute("data-loggedin") === "1";
}

function requireLogin(message) {
  if (!isLoggedIn()) {
    const err = document.getElementById("authError");
    if (err) {
      err.textContent = message || "You need to login first.";
      err.classList.remove("d-none");
    }
    const modalEl = document.getElementById("authModal");
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    } else {
      alert(message || "You need to login first.");
    }
    return false;
  }
  return true;
}

document.getElementById("openLogin")?.addEventListener("click", () => {
  const modalEl = document.getElementById("authModal");
  if (modalEl) new bootstrap.Modal(modalEl).show();
});

/* ── Post modal ───────────────────────────────────────────────── */

function openPostModal(kind) {
  if (!requireLogin("You need to login first.")) return;

  const form = document.getElementById("postForm");
  const title = document.getElementById("postModalTitle");
  const kindInput = document.getElementById("postKind");

  if (!form || !title || !kindInput) return;

  form.reset();

  // Clear image preview
  const preview = document.getElementById("imagePreview");
  if (preview) preview.innerHTML = "";

  const isFound = kind === "found";
  title.textContent = isFound ? "Post a FOUND item" : "Post a LOST item";
  kindInput.value = kind;

  form.action = `/post/${kind}`;

  const modalEl = document.getElementById("postModal");
  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

window.openPostModal = openPostModal;

/* ── Delete countdown timers ──────────────────────────────────── */

function setupCountdowns() {
  document.querySelectorAll("[data-delete-eta]").forEach((el) => {
    const eta = parseInt(el.getAttribute("data-delete-eta"), 10);
    if (!eta) return;

    function tick() {
      const now = Math.floor(Date.now() / 1000);
      const remain = Math.max(0, eta - now);
      el.textContent = remain + "s";
      if (remain > 0) setTimeout(tick, 1000);
      else location.reload();
    }
    tick();
  });
}

/* ── Flash message auto-dismiss ───────────────────────────────── */

function setupFlashAutoDismiss() {
  document.querySelectorAll(".alert-success").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity .3s ease, transform .3s ease";
      el.style.opacity = "0";
      el.style.transform = "translateY(-8px)";
      setTimeout(() => el.remove(), 300);
    }, 8000);
  });
}

/* ── File upload validation ───────────────────────────────────── */

document.getElementById("postForm")?.addEventListener("submit", function (e) {
  const input = this.querySelector('input[type="file"][name="images"]');
  if (!input) return;

  const files = Array.from(input.files || []);
  if (files.length > 3) {
    e.preventDefault();
    alert("Please upload a maximum of 3 images.");
    return;
  }

  const allowed = ["png", "jpg", "jpeg", "webp"];
  for (const f of files) {
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (!allowed.includes(ext)) {
      e.preventDefault();
      alert("Only PNG, JPG, JPEG, or WEBP images are allowed.");
      return;
    }
  }

  // Show loading spinner
  const btnText = document.querySelector("#postSubmitBtn .btn-text");
  const spinner = document.getElementById("postSpinner");
  if (btnText) btnText.textContent = "Posting…";
  if (spinner) spinner.classList.remove("d-none");
});

/* ── Filters modal ────────────────────────────────────────────── */

function setupFilters() {
  const btn = document.getElementById("filtersBtn");
  const modalEl = document.getElementById("filtersModal");
  if (!btn || !modalEl) return;

  const modal = new bootstrap.Modal(modalEl);
  const selCat = document.getElementById("filterCategory");
  const selPlace = document.getElementById("filterPlace");
  const hiddenCat = document.getElementById("hiddenCat");
  const hiddenPlace = document.getElementById("hiddenPlace");
  const form = document.getElementById("searchForm");

  btn.addEventListener("click", () => {
    if (hiddenCat) selCat.value = hiddenCat.value || "";
    if (hiddenPlace) selPlace.value = hiddenPlace.value || "";
    modal.show();
  });

  document.getElementById("filtersClear")?.addEventListener("click", () => {
    if (hiddenCat) hiddenCat.value = "";
    if (hiddenPlace) hiddenPlace.value = "";
    selCat.value = "";
    selPlace.value = "";
  });

  document.getElementById("filtersApply")?.addEventListener("click", () => {
    if (hiddenCat) hiddenCat.value = selCat.value || "";
    if (hiddenPlace) hiddenPlace.value = selPlace.value || "";
    modal.hide();
    form?.submit();
  });
}

/* ── Relative timestamps ("3 h ago") ──────────────────────────── */

function timeAgo(dateStr) {
  const date = new Date(dateStr);
  if (isNaN(date)) return dateStr;           // Fallback if unparseable

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
  return date.toLocaleDateString("en-IN", {
    month: "short", day: "numeric", year: "numeric"
  });
}

function setupTimeago() {
  document.querySelectorAll("time.timeago").forEach((el) => {
    const raw = el.getAttribute("datetime");
    if (raw) {
      el.textContent = timeAgo(raw);
      el.title = raw;            // Tooltip shows exact timestamp
    }
  });
}

/* ── Image preview before upload ──────────────────────────────── */

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

  // Remove individual preview (visual only — can't modify FileList)
  preview.addEventListener("click", (e) => {
    const btn = e.target.closest(".remove-preview");
    if (btn) btn.closest(".preview-thumb").remove();
  });
}

/* ── Lightbox (click thumbnail → full-size) ───────────────────── */

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

/* ── Bootstrap all features on DOM ready ──────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  setupCountdowns();
  setupFlashAutoDismiss();
  setupFilters();
  setupTimeago();
  setupImagePreview();
  setupLightbox();
});