const API_BASE = "";

function getToken() {
  return localStorage.getItem("token");
}

function setToken(token) {
  localStorage.setItem("token", token);
}

function clearToken() {
  localStorage.removeItem("token");
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body instanceof FormData) delete headers["Content-Type"];

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = "/index.html";
    return;
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

async function login(email, password) {
  const body = JSON.stringify({ email, password });
  console.log("login() fetch body:", body);
  const data = await apiFetch("/auth/login", {
    method: "POST",
    body,
  });
  setToken(data.access_token);
  return data;
}

async function getMe() {
  return await apiFetch("/auth/me");
}

function logout() {
  clearToken();
  window.location.href = "/index.html";
}

function requireAuth() {
  if (!getToken()) window.location.href = "/index.html";
}

async function requireAdmin() {
  requireAuth();
  const me = await getMe();
  if (!me.is_admin) window.location.href = "/gear.html";
  return me;
}

function showError(el, msg) {
  el.textContent = msg;
  el.style.display = "block";
}

// File pickers default to the gallery on some phones. Offer an explicit source
// choice before opening a photo input, while leaving desktop file pickers alone.
function choosePhotoSource(input) {
  if (input.dataset.photoSourceReady === "true") {
    delete input.dataset.photoSourceReady;
    return true;
  }

  let picker = document.getElementById("photo-source-picker");
  if (!picker) {
    picker = document.createElement("div");
    picker.id = "photo-source-picker";
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-modal", "true");
    picker.setAttribute("aria-label", "Choose photo source");
    picker.style.cssText = "display:none;position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.5);align-items:center;justify-content:center;padding:1rem";
    picker.innerHTML = `
      <div style="width:min(360px,100%);background:#fff;border-radius:8px;padding:1.25rem;box-shadow:0 8px 24px rgba(0,0,0,.25)">
        <h2 style="margin:0 0 .5rem">Add a photo</h2>
        <p style="margin:0 0 1rem;color:#666">Where would you like to get it from?</p>
        <div style="display:flex;gap:.5rem;flex-wrap:wrap">
          <button type="button" class="btn btn-primary" onclick="openPhotoSource(true)">Take a picture</button>
          <button type="button" class="btn btn-secondary" onclick="openPhotoSource(false)">Choose from gallery</button>
          <button type="button" class="btn" onclick="closePhotoSource()">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(picker);
  }
  picker.photoInput = input;
  picker.style.display = "flex";
  return false;
}

function openPhotoSource(useCamera) {
  const picker = document.getElementById("photo-source-picker");
  const input = picker?.photoInput;
  closePhotoSource();
  if (!input) return;
  if (useCamera) input.setAttribute("capture", "environment");
  else input.removeAttribute("capture");
  input.dataset.photoSourceReady = "true";
  input.click();
}

function closePhotoSource() {
  const picker = document.getElementById("photo-source-picker");
  if (picker) {
    picker.style.display = "none";
    picker.photoInput = null;
  }
}
