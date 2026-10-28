import { fireEvent, render, screen, waitFor, cleanup, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { listenForAppFocus } from "../api/focusRefresh";
import { api } from "../api/client";

let status: Record<string, unknown>;
let statusReads: number;
let failStatus: boolean;
let client: QueryClient;

function Probe() {
  const { session, loading, reauthenticate, refreshError } = useAuth();
  return <><output>{loading ? "loading" : session?.authenticated ? session.reauthenticated_until || "unverified" : "signed out"}</output><input aria-label="unsaved draft" /><button onClick={() => void reauthenticate("synthetic-password")}>Verify</button>{refreshError && <p>refresh failed</p>}</>;
}

beforeEach(() => {
  statusReads = 0; failStatus = false;
  status = { authenticated: true, setup_required: false, csrf_token: "first-csrf", reauthenticated_until: null, user: { id: 1 } };
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  focusManager.setEventListener(listenForAppFocus);
  vi.stubGlobal("fetch", vi.fn(async (path: string) => {
    if (path === "/api/auth/status") { statusReads++; if (failStatus) throw new TypeError("offline"); return Response.json(status); }
    if (path === "/api/auth/reauthenticate") return Response.json({ reauthenticated_until: "2099-01-01T00:00:00Z" });
    throw new Error(`Unexpected request ${path}`);
  }));
});
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); vi.useRealTimers(); });

async function mount() {
  render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
  await screen.findByText("unverified");
}

describe("session refresh", () => {
  it("expires a server-rejected grant immediately even if refreshing status fails", async () => {
    status = { ...status, reauthenticated_until: "2099-01-01T00:00:00Z" };
    render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
    await screen.findByText("2099-01-01T00:00:00Z");
    failStatus = true;
    vi.mocked(fetch).mockImplementationOnce(async () => Response.json({ error: { code: "FORBIDDEN", message: "Recent password verification required" } }, { status: 403 }));
    await act(async () => { await expect(api("/api/vault/backup")).rejects.toMatchObject({ status: 403 }); });
    await waitFor(() => expect(Date.parse(screen.getByRole("status").textContent!)).toBeLessThan(Date.now()));
    await screen.findByText("refresh failed");
  });

  it("does not expire verification for unrelated forbidden responses", async () => {
    status = { ...status, reauthenticated_until: "2099-01-01T00:00:00Z" };
    render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
    await screen.findByText("2099-01-01T00:00:00Z");
    const reads = statusReads;
    vi.mocked(fetch).mockImplementationOnce(async () => Response.json({ error: { code: "FORBIDDEN", message: "Invalid CSRF token" } }, { status: 403 }));
    await act(async () => { await expect(api("/api/vault/backup")).rejects.toMatchObject({ status: 403 }); });
    expect(screen.getByText("2099-01-01T00:00:00Z")).toBeInTheDocument();
    expect(statusReads).toBe(reads);
  });

  it("syncs on focus and visibility without clearing drafts, recovers after failure, and detects logout", async () => {
    await mount();
    fireEvent.change(screen.getByLabelText("unsaved draft"), { target: { value: "keep this" } });
    status = { ...status, reauthenticated_until: "2099-02-01T00:00:00Z" };
    act(() => window.dispatchEvent(new Event("focus")));
    await screen.findByText("2099-02-01T00:00:00Z");
    expect(screen.getByLabelText("unsaved draft")).toHaveValue("keep this");
    failStatus = true;
    act(() => window.dispatchEvent(new Event("focus")));
    await screen.findByText("refresh failed");
    expect(screen.getByLabelText("unsaved draft")).toHaveValue("keep this");
    failStatus = false;
    status = { authenticated: false, setup_required: false };
    act(() => window.dispatchEvent(new Event("visibilitychange")));
    await screen.findByText("signed out");
    expect(screen.queryByText("refresh failed")).not.toBeInTheDocument();
  });

  it("refreshes authenticated sessions periodically while remaining mounted", async () => {
    vi.useFakeTimers();
    render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
    await vi.waitFor(() => expect(screen.queryByText("unverified")).toBeInTheDocument());
    const previousReads = statusReads;
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(statusReads).toBeGreaterThan(previousReads);
  });

  it("cancels an older status request before applying renewed authorization", async () => {
    await mount();
    let resolveOld!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    act(() => window.dispatchEvent(new Event("focus")));
    await waitFor(() => expect(resolveOld).toBeTypeOf("function"));
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    await screen.findByText("2099-01-01T00:00:00Z");
    await act(async () => { resolveOld(Response.json(status)); });
    expect(screen.getByText("2099-01-01T00:00:00Z")).toBeInTheDocument();
  });
});
