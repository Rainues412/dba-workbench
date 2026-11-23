import { invoke, isTauri } from "@tauri-apps/api/core";

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
let vaultAccessToken = "";
const desktopReadCommands = new Map([
  ["/api/dashboard/stats", "dashboard_stats"],
  ["/api/dashboard/recent-tasks", "dashboard_recent_tasks"],
  ["/api/dashboard/database-distribution", "dashboard_database_distribution"],
  ["/api/resources/facets", "resources_facets"],
  ["/api/scripts/recent-views", "script_recent_views"],
  ["/api/auth/status", "account_status"],
  ["/api/vault/profile", "vault_profile"],
]);
export const REAUTH_REQUIRED_EVENT = "dba:reauth-required";
export const VAULT_LOCKED_EVENT = "dba:vault-locked";
export const VAULT_ACCESS_EVENT = "dba:vault-access-changed";

export function setCsrfToken(token?: string | null) {
  csrfToken = token ?? "";
}

export function setVaultAccessToken(token = "") {
  if (vaultAccessToken === token) return;
  vaultAccessToken = token;
  window.dispatchEvent(new Event(VAULT_ACCESS_EVENT));
}

export function hasVaultAccessToken() {
  return Boolean(vaultAccessToken);
}

export async function api<T>(
  path: string,
  init: RequestInit & { revision?: number } = {},
): Promise<T> {
  if (isTauri()) {
    const method = (init.method ?? "GET").toUpperCase();
    const signal = init.signal ?? undefined;
    if (method === "GET") {
      const command = desktopReadCommands.get(path);
      if (command) return invokeDesktop<T>(command, {}, signal);
      const library = /^\/api\/(scripts|articles)\/(facets|\d+)$/.exec(path);
      if (library) {
        const [, name, target] = library;
        if (target === "facets") return invokeDesktop<T>("library_facets", { library: name }, signal);
        return invokeDesktop<T>("library_detail", { library: name, id: Number(target) }, signal);
      }
      const history = /^\/api\/scripts\/(\d+)\/versions\/(\d+)$/.exec(path);
      if (history) return invokeDesktop<T>("script_version", { id: Number(history[1]), version: Number(history[2]) }, signal);
    } else if (method === "POST") {
      const view = /^\/api\/scripts\/(\d+)\/view$/.exec(path);
      if (view) return invokeDesktop<T>("script_record_view", { id: Number(view[1]), csrfToken });
    }
  }

  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes((init.method ?? "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  if (init.revision !== undefined) headers.set("If-Match", String(init.revision));
  if (vaultAccessToken && path.startsWith("/api/vault/") && !headers.has("X-DBA-Vault-Token")) headers.set("X-DBA-Vault-Token", vaultAccessToken);
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    // Other 403s (CSRF, directory permissions) must not invalidate the grant.
    if (response.status === 403 && (body.error?.message ?? body.detail) === "Recent password verification required" && typeof window !== "undefined") {
      window.dispatchEvent(new Event(REAUTH_REQUIRED_EVENT));
    }
    if (response.status === 403 && (body.error?.message ?? body.detail) === "Vault unlock required") {
      window.dispatchEvent(new Event(VAULT_LOCKED_EVENT));
    }
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
  desktop?: boolean;
  vault_password_only?: boolean;
  manual_login_available?: boolean;
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

async function invokeDesktop<T>(command: string, args: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted();
  try {
    const result = await invoke<T>(command, args);
    signal?.throwIfAborted();
    return result;
  } catch (reason) {
    signal?.throwIfAborted();
    const error = reason as Partial<{ status: number; message: string }> | null;
    throw new ApiError(error?.status ?? 500, "DESKTOP_REQUEST_FAILED", error?.message ?? "读取或保存本机数据失败，请重试。");
  }
}

function nativeEntity(path: string) {
  if (!isTauri()) return null;
  if (path === "/api/tasks/") return "tasks";
  if (path === "/api/resources/") return "resources";
  if (path === "/api/scripts/") return "scripts";
  if (path === "/api/articles/") return "articles";
  if (path === "/api/customers/") return "customers";
  return null;
}

function invokeEntity<T>(module: NonNullable<ReturnType<typeof nativeEntity>>, action: string, args: Record<string, unknown>) {
  if (module === "scripts" || module === "articles") {
    return invokeDesktop<T>(`library_${action}`, { library: module, ...args });
  }
  return invokeDesktop<T>(`${module}_${action}`, args);
}

async function sessionStatus(signal?: AbortSignal): Promise<Session> {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("desktop");
  if (token) {
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    window.sessionStorage.setItem("dba-desktop-token", token);
  }
  const desktopToken = token || window.sessionStorage.getItem("dba-desktop-token");
  let session = await api<Session>("/api/auth/status", { signal });
  if (desktopToken && !session.authenticated) {
    await api<void>("/api/auth/desktop", { method: "POST", headers: { "X-DBA-Desktop-Token": desktopToken }, signal });
    session = await api<Session>("/api/auth/status", { signal });
  }
  return desktopToken ? { ...session, desktop: true } : session;
}

export const authApi = {
  status: sessionStatus,
  setup: (username: string, password: string) =>
    api<Session>("/api/auth/setup", { method: "POST", body: jsonBody({ username, password }) }),
  login: (username: string, password: string) =>
    api<Session>("/api/auth/login", { method: "POST", body: jsonBody({ username, password }) }),
  reauthenticate: (password: string) =>
    api<{ reauthenticated_until: string }>("/api/auth/reauthenticate", {
      method: "POST",
      body: jsonBody({ password }),
    }),
};

export const entityApi = {
  list: <T extends Entity>(path: string, page: number, keyword: string, filters: Record<string, string> = {}, pageSize = 20, signal?: AbortSignal) => {
    const module = nativeEntity(path);
    if (module === "tasks") {
      return invokeDesktop<Page<T>>("tasks_list", {
        filter: { page, pageSize, keyword, status: filters.status ?? "", priority: filters.priority ?? "",
          archived: filters.archived === "1", overdue: filters.overdue === "1" },
      }, signal);
    }
    if (module === "resources") {
      return invokeDesktop<Page<T>>("resources_list", {
        filter: { page, pageSize, keyword, kind: filters.kind ?? "", category: filters.category ?? "",
          tag: filters.tag ?? "", wbDb: filters.wb_db ?? "", favoriteOnly: filters.favorite_only === "1" },
      }, signal);
    }
    if (module === "scripts" || module === "articles") {
      const scripts = module === "scripts";
      return invokeDesktop<Page<T>>("library_list", {
        library: module,
        filter: { page, pageSize, keyword, database: filters[scripts ? "db_type" : "wb_db"] ?? "",
          category: filters[scripts ? "wb_type" : "category"] ?? "", tag: filters.tag ?? "",
          favoriteOnly: filters.favorite_only === "1", locateId: filters.locate_id ? Number(filters.locate_id) : null,
          autoPin: scripts && filters.auto_pin === "1" },
      }, signal);
    }
    if (module === "customers") {
      return invokeDesktop<Page<T>>("customers_list", {
        filter: { page, pageSize, keyword, status: filters.status ?? "",
          locateId: filters.locate_id ? Number(filters.locate_id) : null },
      }, signal);
    }
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (keyword) params.set("keyword", keyword);
    for (const [field, value] of Object.entries(filters)) if (value) params.set(field, value);
    return api<Page<T>>(`${path}?${params}`, { signal });
  },
  detail: <T extends Entity>(path: string, id: number) => {
    const module = nativeEntity(path);
    return module ? invokeEntity<T>(module, "detail", { id }) : api<T>(`${path}${id}`);
  },
  create: <T extends Entity>(path: string, body: Record<string, unknown>) => {
    const module = nativeEntity(path);
    return module ? invokeEntity<T>(module, "create", { input: body, csrfToken })
      : api<T>(path, { method: "POST", body: jsonBody(body) });
  },
  update: <T extends Entity>(path: string, id: number, revision: number, body: Record<string, unknown>) => {
    const module = nativeEntity(path);
    return module ? invokeEntity<T>(module, "update", { id, revision, input: body, csrfToken })
      : api<T>(`${path}${id}`, { method: "PUT", revision, body: jsonBody(body) });
  },
  remove: (path: string, id: number, revision: number) => {
    const module = nativeEntity(path);
    return module ? invokeEntity<void>(module, "delete", { id, revision, csrfToken }).then(() => ({ ok: true }))
      : api<{ ok: boolean }>(`${path}${id}`, { method: "DELETE", revision });
  },
};

export async function completeDashboardTask(taskId: number, revision: number): Promise<void> {
  await entityApi.update("/api/tasks/", taskId, revision, { status: "已完成" });
}

export function searchWorkspace<T>(query: string, signal: AbortSignal): Promise<T> {
  if (isTauri()) return invokeDesktop<T>("global_search", { query, limit: 0 }, signal);
  return api<T>(`/api/search/?${new URLSearchParams({ q: query, limit: "0" })}`, { signal });
}
