// API client for the SECURED backend. Every request carries the Bearer token.
// Token is held in module scope, set at login.

let _token = null;

export function setToken(token) {
  _token = token;
}
export function getToken() {
  return _token;
}
export function clearToken() {
  _token = null;
}

function authHeaders(extra = {}) {
  if (!_token) throw new Error('Not authenticated');
  return { Authorization: `Bearer ${_token}`, ...extra };
}

async function handle(res) {
  if (res.status === 401) {
    clearToken();
    throw new Error('未授权（401）：请重新登录');
  }
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

// ---- Auth probe: validate a token by calling a lightweight authed endpoint ----
export async function login(token) {
  const res = await fetch('/api/collection/stats', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) throw new Error('无效的 Token');
  if (!res.ok) throw new Error(`登录校验失败: ${res.status}`);
  const stats = await res.json();
  _token = token; // valid -> persist in module scope
  return stats;
}

// ---- Secure liveness bound flow ----
export async function createBoundSession() {
  const res = await fetch('/api/secure/liveness/session', {
    method: 'POST',
    headers: authHeaders(),
  });
  return handle(res); // { attemptId, sessionId, accountId, state }
}

export async function completeAttempt(attemptId, sessionId) {
  const form = new FormData();
  form.append('session_id', sessionId);
  const res = await fetch(
    `/api/secure/liveness/attempt/${encodeURIComponent(attemptId)}/complete`,
    { method: 'POST', headers: authHeaders(), body: form }
  );
  return handle(res);
}

// ---- Collection 1:N (authenticated) ----
export async function getStats() {
  const res = await fetch('/api/collection/stats', { headers: authHeaders() });
  return handle(res);
}

export async function listUsers() {
  const res = await fetch('/api/collection/users', { headers: authHeaders() });
  return handle(res);
}

export async function deleteUser(userId) {
  const res = await fetch(`/api/collection/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handle(res);
}

export async function searchByImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/collection/search', {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return handle(res);
}

export async function enrollByImage(file, userId) {
  const form = new FormData();
  form.append('file', file);
  if (userId) form.append('user_id', userId);
  const res = await fetch('/api/collection/enroll', {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return handle(res);
}
