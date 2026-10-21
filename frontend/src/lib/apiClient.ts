// Thin fetch wrapper for the FastAPI backend, reached through this site's own
// /api (next.config.ts), so the session cookie works.
//
// The sign-in (access) token is kept in memory only, never in storage, so a
// script injected into the page can't read it from there. It lasts minutes;
// when a request comes back 401 it's renewed once from the session cookie
// (HttpOnly: the page can't read it either) and the request sent again. If
// the session has ended (signed out elsewhere, idle too long, a password
// change), the app is told (setSessionHandlers) and shows the sign-in page.
// If the server can't be reached (restarting, say), nobody is signed out.

import { CHANGE_PASSWORD_PATH } from "@/lib/paths";
import type { Token } from "@/lib/types";

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

let accessToken: string | null = null;

export function getToken(): string | null {
  return accessToken;
}

export function setToken(token: string): void {
  accessToken = token;
}

export function clearToken(): void {
  accessToken = null;
}

// Where tokens were kept before (Phase 2e): removed if still there.
if (typeof window !== "undefined") window.localStorage.removeItem("auditmind_token");

type SessionHandlers = {
  /** The session ended (refresh refused): sign the app out, saying why. */
  onSessionEnded(message: string): void;
  /** Every page but Change password is refused until it's changed. */
  onPasswordChangeRequired(): void;
};

// Until the app sets its own: go to the page.
const DEFAULT_HANDLERS: SessionHandlers = {
  onSessionEnded: () => window.location.assign("/login"),
  onPasswordChangeRequired: () => window.location.assign(CHANGE_PASSWORD_PATH),
};
let handlers = DEFAULT_HANDLERS;

/** The app's handlers; null: back to the defaults. */
export function setSessionHandlers(next: SessionHandlers | null): void {
  handlers = next ?? DEFAULT_HANDLERS;
}

function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
}

// Sent with every request: refresh and logout, which act on the cookie
// alone, refuse requests without it (another site's page can't add it).
const APP_HEADER = { "X-Requested-With": "AuditMind" };
// The app's own polling: checked like any request, but not counted as the
// person being active, so an open page still signs out when left idle.
const BACKGROUND_HEADER = { "X-Activity": "background" };

const UNREACHABLE = "Cannot reach the AuditMind API. Is the backend running?";

let refreshing: Promise<Token | null> | null = null;

/** A new access token from the session cookie (one request at a time,
 * shared by everyone waiting); null if the session has ended. Throws an
 * ApiError if the server can't answer (down, restarting): the session may
 * well still be open. */
export function refreshAccessToken(background = false): Promise<Token | null> {
  refreshing ??= (async () => {
    let res: Response;
    try {
      res = await fetch(`${baseUrl()}/auth/refresh`, {
        method: "POST",
        headers: { Accept: "application/json", ...APP_HEADER, ...(background ? BACKGROUND_HEADER : {}) },
        credentials: "same-origin",
      });
    } catch {
      throw new ApiError(0, UNREACHABLE);
    }
    if (res.status === 401) return null;
    if (!res.ok) throw new ApiError(res.status, UNREACHABLE);
    const token = (await res.json()) as Token;
    setToken(token.access_token);
    return token;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

type RequestOptions = { background?: boolean; headers?: Record<string, string> };

async function request<T>(method: string, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  let payload: BodyInit | undefined;
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...APP_HEADER,
    ...options.headers,
    ...(options.background ? BACKGROUND_HEADER : {}),
  };
  if (body instanceof FormData) {
    payload = body; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const send = async (token: string | null) => {
    try {
      return await fetch(`${baseUrl()}${path}`, {
        method,
        headers: token ? { ...headers, Authorization: `Bearer ${token}` } : headers,
        body: payload,
        credentials: "same-origin",
      });
    } catch {
      throw new ApiError(0, UNREACHABLE);
    }
  };

  const token = getToken();
  let res = await send(token);
  // Signed in, and refused: the access token ran out (renew it and try once
  // more) or the session ended. Not for /auth itself: a wrong password is a
  // 401 too.
  if (res.status === 401 && token && !path.startsWith("/auth/")) {
    // Another request may have renewed it meanwhile.
    const latest = getToken();
    const next =
      latest && latest !== token ? latest : (await refreshAccessToken(options.background))?.access_token;
    if (next) res = await send(next);
    if (!next || res.status === 401) {
      clearToken();
      const message = sessionEndedMessage(await res.json().catch(() => null));
      handlers.onSessionEnded(message);
      throw new ApiError(401, message);
    }
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = (data as { detail?: unknown } | null)?.detail;
    if (res.status === 403 && (detail as { code?: string } | null)?.code === "password_change_required") {
      handlers.onPasswordChangeRequired();
    }
    throw new ApiError(res.status, errorMessage(data, res.statusText), detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// Why the session ended, when the server said (idle too long, expired);
// else a general message.
function sessionEndedMessage(data: unknown): string {
  const detail = (data as { detail?: { code?: string; message?: string } } | null)?.detail;
  return detail?.code === "session_ended" && detail.message
    ? detail.message
    : "Your session has ended. Please sign in again.";
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
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>("POST", path, body, options),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: (path: string) => request<void>("DELETE", path),
  /** Multipart upload: the file, plus any extra form fields. */
  upload: <T>(path: string, file: File, fields: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file);
    for (const [name, value] of Object.entries(fields)) form.append(name, value);
    return request<T>("POST", path, form);
  },
  /** Auth headers for direct fetch() calls (e.g. streaming downloads). */
  authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}`, ...APP_HEADER } : { ...APP_HEADER };
  },
};

/** Alias for components that import `apiClient` directly. */
export const apiClient = api;
