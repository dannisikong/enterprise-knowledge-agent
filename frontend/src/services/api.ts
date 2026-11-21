const configuredBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const apiUrl = (path: string) => configuredBase ? configuredBase + path : "/api" + path;

type SessionPayload = { session_id: string; token: string; expires_at: string };
const SESSION_KEY = "knowledge-agent-session-token";

export async function ensureSession(): Promise<string> {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const response = await fetch(apiUrl("/session"), { method: "POST" });
  if (!response.ok) throw new Error("无法创建匿名会话，请稍后重试。");
  const payload = await response.json() as SessionPayload;
  if (!payload.token) throw new Error("会话初始化失败。");
  sessionStorage.setItem(SESSION_KEY, payload.token);
  return payload.token;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await ensureSession();
  const headers = new Headers(init.headers);
  headers.set("X-Session-Token", token);
  return fetch(apiUrl(path), { ...init, headers });
}
