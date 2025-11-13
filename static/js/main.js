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

function openPostModal(kind) {
  if (!requireLogin("You need to login first.")) return;

  const form = document.getElementById("postForm");
  const title = document.getElementById("postModalTitle");
  const kindInput = document.getElementById("postKind");

  if (!form || !title || !kindInput) return;

  form.reset();

  const isFound = kind === "found";
  title.textContent = isFound ? "Post a FOUND item" : "Post a LOST item";
  kindInput.value = kind;

  form.action = `/post/${kind}`;

  const modalEl = document.getElementById("postModal");
  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

window.openPostModal = openPostModal;

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

document.addEventListener("DOMContentLoaded", setupCountdowns);
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".alert-success").forEach((el) => {
    setTimeout(() => el.remove(), 10000); // 10,000 ms = 10s
  });
});

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
});

document.addEventListener("DOMContentLoaded", () => {
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
});