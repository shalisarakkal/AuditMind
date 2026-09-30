// Thin fetch wrapper for the FastAPI backend. The JWT lives in localStorage
// (only ever read in the browser); a 401 on an authenticated request means the
// session expired, so the token is dropped and the user sent to /login.

const TOKEN_KEY = "auditmind_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** The error body's detail, when it's more than a message. */
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

// 127.0.0.1, not localhost: on Windows localhost tries IPv6 first, where
// the backend doesn't listen, costing ~2 s per new connection.
function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(`${baseUrl()}${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the AuditMind API. Is the backend running?");
  }

  if (res.status === 401 && token) {
    clearToken();
    window.location.assign("/login");
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, errorMessage(data, res.statusText), detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// FastAPI errors: {detail: "text"}, {detail: {message, ...}} or, for
// validation, {detail: [{msg, loc}]}.
function errorMessage(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  const message = (detail as { message?: unknown } | null)?.message;
  if (typeof message === "string") return message;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = d.loc?.[d.loc.length - 1];
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return fallback || "Request failed";
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: (path: string) => request<void>("DELETE", path),
  /** Multipart upload: the file, plus any extra form fields. */
  upload: <T>(path: string, file: File, fields: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file);
    for (const [name, value] of Object.entries(fields)) form.append(name, value);
    return request<T>("POST", path, form);
  },
};
