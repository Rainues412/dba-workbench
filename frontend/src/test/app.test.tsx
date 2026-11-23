import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { startVaultAutoLock, VAULT_IDLE_TIMEOUT_MS } from "../vault/autoLock";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe("application shell", () => {
  it("propts for the desktop launcher when the local session is missing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ authenticated: false, setup_required: false })));
    render(<App />);
    expect(await screen.findByText("请从桌面快捷方式打开 DBA 工作台。")).toBeInTheDocument();
    expect(screen.queryByLabelText("用户名")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("登录密码")).not.toBeInTheDocument();
  });

  it("shows first-owner setup only when enabled by the development server", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ authenticated: false, setup_required: true, manual_login_available: true }), { status: 200, headers: { "Content-Type": "application/json" } })));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "创建首位 Owner" })).toBeInTheDocument();
    expect(screen.getByLabelText("登录密码")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("登录密码")).toHaveAttribute("minlength", "9");
    expect(screen.queryByText("系统故障")).not.toBeInTheDocument();
  });
});

describe("vault automatic locking", () => {
  it("stays unlocked after five minutes and locks at fifteen idle minutes", () => {
    vi.useFakeTimers();
    const lock = vi.fn();
    const stop = startVaultAutoLock(lock);
    vi.advanceTimersByTime(5 * 60 * 1000);
    expect(lock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10 * 60 * 1000 - 1);
    expect(lock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(lock).toHaveBeenCalledExactlyOnceWith("idle");
    stop();
  });

  it("does not lock on a short window switch, but still expires while hidden", () => {
    vi.useFakeTimers();
    const lock = vi.fn();
    const stop = startVaultAutoLock(lock);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(1000);
    window.dispatchEvent(new Event("focus"));
    expect(lock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(VAULT_IDLE_TIMEOUT_MS);
    expect(lock).toHaveBeenCalledExactlyOnceWith("idle");
    stop();
  });

  it("checks elapsed time on return even when background timers were suspended", () => {
    vi.useFakeTimers();
    const lock = vi.fn();
    const stop = startVaultAutoLock(lock);
    vi.setSystemTime(Date.now() + VAULT_IDLE_TIMEOUT_MS + 1);
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new KeyboardEvent("keydown"));
    expect(lock).toHaveBeenCalledExactlyOnceWith("idle");
    stop();
  });

  it("locks after fifteen idle minutes and activity resets the timer", () => {
    vi.useFakeTimers();
    const lock = vi.fn();
    const stop = startVaultAutoLock(lock);
    vi.advanceTimersByTime(VAULT_IDLE_TIMEOUT_MS - 1);
    expect(lock).not.toHaveBeenCalled();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
    vi.advanceTimersByTime(VAULT_IDLE_TIMEOUT_MS - 1);
    expect(lock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(lock).toHaveBeenCalledWith("idle");
    stop();
  });
});
