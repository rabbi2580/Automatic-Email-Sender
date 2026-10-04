// Thin API client: attaches the access token, refreshes it once on 401, surfaces readable errors.
const configuredApi = process.env.NEXT_PUBLIC_API_URL;
const browserApi = typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.hostname}:8000/api/v1`
  : "http://localhost:8000/api/v1";
export const API = configuredApi || browserApi;

const ACCESS = "jaa_access";
const REFRESH = "jaa_refresh";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  del: (k: string) => { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

export const tokens = {
  refresh: () => store.get(REFRESH),
  set(a: string, r: string) { store.set(ACCESS, a); store.set(REFRESH, r); },
  clear() { store.del(ACCESS); store.del(REFRESH); },
  has: () => !!store.get(ACCESS),
};

function message(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return fallback;
}

let refreshing: Promise<boolean> | null = null;
async function refresh(): Promise<boolean> {
  const rt = store.get(REFRESH);
  if (!rt) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) });
      if (!r.ok) return false;
      const j = await r.json();
      tokens.set(j.access_token, j.refresh_token);
      return true;
    } catch { return false; } finally { setTimeout(() => { refreshing = null; }, 0); }
  })();
  return refreshing;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData; auth?: boolean } = {}): Promise<T> {
  const doFetch = async () => {
    const headers: Record<string, string> = {};
    const at = store.get(ACCESS);
    if (opts.auth !== false && at) headers.Authorization = `Bearer ${at}`;
    let body: BodyInit | undefined;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
    try {
      return await fetch(`${API}${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body });
    } catch (error) {
      const host = API.replace(/\/api\/v1$/, "");
      throw new Error(`Cannot reach the API at ${host}. Start the backend and check CORS/API URL.`);
    }
  };
  let res = await doFetch();
  if (res.status === 401 && opts.auth !== false && (await refresh())) res = await doFetch();
  if (res.status === 401 && opts.auth !== false) {
    tokens.clear();
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) location.href = "/login";
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json().catch(() => null) : null;
  if (!res.ok) throw new ApiError(res.status, message(data?.detail, `Request failed (${res.status})`), data?.detail);
  return data as T;
}

/** Download a file behind auth (export, documents) via a short-lived signed URL. */
export async function openSigned(path: string) {
  const r = await api<{ url: string }>(path);
  const u = r.url.startsWith("http") ? r.url : API.replace(/\/api\/v1$/, "") + r.url;
  window.open(u, "_blank", "noopener");
}

export async function downloadJson(path: string, filename: string) {
  const at = store.get(ACCESS);
  const res = await fetch(`${API}${path}`, { headers: at ? { Authorization: `Bearer ${at}` } : {} });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
