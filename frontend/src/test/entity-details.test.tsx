import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EntityDetails } from "../components/EntityDetails";
import { Entity, setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });

function show(module: string, item: Entity) {
  const onRefresh = vi.fn(async () => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<MemoryRouter><QueryClientProvider client={client}><EntityDetails module={module} item={item} onRefresh={onRefresh} /></QueryClientProvider></MemoryRouter>);
  return onRefresh;
}
const script = { id: 7, revision: 9, version: 4, versions: [{ version: 3, created_at: "2026-10-18" }] };

describe("script history details", () => {
  it("reads selected history and restores with the current revision and CSRF token", async () => {
    const fetch = vi.fn(async (path: string) => Response.json(path.endsWith("/versions/3") ? { content: "SELECT 3;" } : { ok: true }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    setCsrfToken("history-csrf");
    const onRefresh = show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    expect(await screen.findByLabelText("历史正文")).toHaveValue("SELECT 3;");
    expect(screen.getByLabelText("历史正文")).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "恢复此版本为当前正文" }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    const [path, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(path).toBe("/api/scripts/7");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ content: "SELECT 3;" });
    expect(new Headers(init.headers).get("If-Match")).toBe("9");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("history-csrf");
  });

  it("shows history errors without enabling restore and permits retry", async () => {
    let failed = true;
    vi.stubGlobal("fetch", vi.fn(async () => failed ? Response.json({}, { status: 500 }) : Response.json({ content: "retried content" })));
    show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    await screen.findByText("历史版本加载失败");
    expect(screen.queryByRole("button", { name: "恢复此版本为当前正文" })).not.toBeInTheDocument();
    failed = false;
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByLabelText("历史正文")).toHaveValue("retried content");
  });

  it("does not retry an optimistic conflict with an unverified revision", async () => {
    const fetch = vi.fn(async (path: string) => path.endsWith("/versions/3") ? Response.json({ content: "SELECT 3;" }) : Response.json({ error: { message: "版本冲突" } }, { status: 409 }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onRefresh = show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    await screen.findByLabelText("历史正文");
    fireEvent.click(screen.getByRole("button", { name: "恢复此版本为当前正文" }));
    await screen.findByText("版本冲突");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
