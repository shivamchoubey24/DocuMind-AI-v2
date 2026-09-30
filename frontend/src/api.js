import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("documind_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      sessionStorage.removeItem("documind_token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export async function registerUser(email, password, fullName) {
  const { data } = await api.post("/auth/register", { email, password, full_name: fullName });
  return data;
}

export async function loginUser(email, password) {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const { data } = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return data;
}

export async function fetchMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

export async function uploadDocuments(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const { data } = await api.post("/documents/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function listDocuments() {
  const { data } = await api.get("/documents");
  return data;
}

export async function deleteDocument(id) {
  await api.delete(`/documents/${id}`);
}

export async function listSessions() {
  const { data } = await api.get("/chat/sessions");
  return data;
}

export async function createSession(title, documentIds) {
  const { data } = await api.post("/chat/sessions", { title, document_ids: documentIds || null });
  return data;
}

export async function deleteSession(id) {
  await api.delete(`/chat/sessions/${id}`);
}

export async function renameSession(id, title) {
  const { data } = await api.patch(`/chat/sessions/${id}`, { title });
  return data;
}

// The file endpoint is opened directly by an <iframe> (for inline preview),
// which can't send an Authorization header — so the token goes as a query
// param instead, same as api.js does for streamChat.
export function getDocumentFileUrl(documentId) {
  const token = sessionStorage.getItem("documind_token");
  const base = api.defaults.baseURL.replace(/\/$/, "");
  return `${base}/documents/${documentId}/file?token=${encodeURIComponent(token || "")}`;
}

// Used by DocumentPreviewModal to confirm the file actually exists before
// pointing an <iframe> at it, so a stale/deleted-document citation shows our
// own message instead of the browser's native "file not found" page.
export async function checkDocumentFileExists(documentId) {
  try {
    const { data } = await api.get(`/documents/${documentId}/file/exists`);
    return Boolean(data.exists);
  } catch (e) {
    return false;
  }
}

export async function setSessionScope(sessionId, documentIds) {
  const { data } = await api.patch(`/chat/sessions/${sessionId}/scope`, { document_ids: documentIds });
  return data;
}

export async function getMessages(sessionId) {
  const { data } = await api.get(`/chat/sessions/${sessionId}/messages`);
  return data;
}

/**
 * Streams a chat answer token-by-token via Server-Sent Events using fetch,
 * since axios doesn't support streaming SSE bodies in the browser.
 * Calls onEvent(parsedJson) for every SSE "data:" line received.
 */
export async function streamChat(sessionId, question, onEvent, signal) {
  const token = sessionStorage.getItem("documind_token");
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  const resp = await fetch(`${base}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ session_id: sessionId, question }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    let message = `Request failed with status ${resp.status}`;
    try {
      const errJson = await resp.json();
      message = errJson.detail || message;
    } catch {
      const text = await resp.text().catch(() => "");
      if (text) message = text;
    }
    throw new Error(message);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;
      try {
        onEvent(JSON.parse(jsonStr));
      } catch {
        // ignore malformed chunk
      }
    }
  }
}
