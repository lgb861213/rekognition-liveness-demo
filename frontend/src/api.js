// Thin client for the FastAPI backend. Requests are proxied via Vite (/api).

export async function createLivenessSession() {
  const res = await fetch('/api/liveness/session', { method: 'POST' });
  if (!res.ok) throw new Error(`createSession failed: ${res.status}`);
  return res.json(); // { sessionId }
}

export async function verifyAndEnroll(sessionId) {
  const res = await fetch(
    `/api/liveness/session/${sessionId}/verify-enroll`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(`verify-enroll failed: ${res.status}`);
  return res.json();
}

export async function getLivenessResult(sessionId) {
  const res = await fetch(`/api/liveness/session/${sessionId}/result`);
  if (!res.ok) throw new Error(`result failed: ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch('/api/collection/stats');
  if (!res.ok) throw new Error(`stats failed: ${res.status}`);
  return res.json(); // { collectionId, faceCount, userCount, exists }
}

export async function listUsers() {
  const res = await fetch('/api/collection/users');
  if (!res.ok) throw new Error(`listUsers failed: ${res.status}`);
  return res.json(); // { users: [{userId, status, faceIds}] }
}

export async function deleteUser(userId) {
  const res = await fetch(`/api/collection/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`deleteUser failed: ${res.status}`);
  return res.json();
}

export async function searchByImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/collection/search', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(`search failed: ${res.status}`);
  return res.json();
}

export async function enrollByImage(file, userId) {
  const form = new FormData();
  form.append('file', file);
  if (userId) form.append('user_id', userId);
  const res = await fetch('/api/collection/enroll', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(`enroll failed: ${res.status}`);
  return res.json();
}
