type ApiErrorBody = {
  error?: { code?: string; message?: string; request_id?: string };
  detail?: string;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
  }
}

let csrfToken = "";

export function setCsrfToken(token?: string | null) {
  csrfToken = token ?? "";
}

export async function api<T>(
  path: string,
  init: RequestInit & { revision?: number } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes((init.method ?? "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  if (init.revision !== undefined) headers.set("If-Match", String(init.revision));
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(
      response.status,
      body.error?.code ?? "REQUEST_FAILED",
      body.error?.message ?? body.detail ?? `HTTP ${response.status}`,
      body.error?.request_id,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export type Session = {
  authenticated: boolean;
  setup_required: boolean;
  csrf_token?: string;
  reauthenticated_until?: string | null;
  reauth_minutes?: number;
  user?: { id: number; username: string; roles: string[] };
};

export type Page<T> = {
  total: number;
  items: T[];
  page: number;
  page_size: number;
  pages: number;
  has_next: boolean;
  has_previous: boolean;
};

export type Entity = Record<string, unknown> & { id: number; revision: number };

export const authApi = {
  status: () => api<Session>("/api/auth/status"),
  setup: (username: string, password: string) =>
    api<Session>("/api/auth/setup", { method: "POST", body: jsonBody({ username, password }) }),
  login: (username: string, password: string) =>
    api<Session>("/api/auth/login", { method: "POST", body: jsonBody({ username, password }) }),
  logout: () => api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  reauthenticate: (password: string) =>
    api<{ reauthenticated_until: string }>("/api/auth/reauthenticate", {
      method: "POST",
      body: jsonBody({ password }),
    }),
};

export const entityApi = {
  list: <T extends Entity>(path: string, page: number, keyword: string, filters: Record<string, string> = {}) => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (keyword) params.set("keyword", keyword);
    for (const [field, value] of Object.entries(filters)) if (value) params.set(field, value);
    return api<Page<T>>(`${path}?${params}`);
  },
  detail: <T extends Entity>(path: string, id: number) => api<T>(`${path}${id}`),
  create: <T extends Entity>(path: string, body: Record<string, unknown>) =>
    api<T>(path, { method: "POST", body: jsonBody(body) }),
  update: <T extends Entity>(path: string, id: number, revision: number, body: Record<string, unknown>) =>
    api<T>(`${path}${id}`, { method: "PUT", revision, body: jsonBody(body) }),
  remove: (path: string, id: number, revision: number) =>
    api<{ ok: boolean }>(`${path}${id}`, { method: "DELETE", revision }),
};
