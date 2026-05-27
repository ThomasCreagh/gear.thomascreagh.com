const API_BASE = "http://localhost:8000";

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
  const data = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
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
