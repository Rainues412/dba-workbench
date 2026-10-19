import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { startVaultAutoLock, VAULT_IDLE_TIMEOUT_MS } from "../vault/autoLock";

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("application shell", () => {
  it("shows first-owner setup without fake dashboard data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ authenticated: false, setup_required: true }), { status: 200, headers: { "Content-Type": "application/json" } })));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "创建首位 Owner" })).toBeInTheDocument();
    expect(screen.getByLabelText("登录密码")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("登录密码")).toHaveAttribute("minlength", "9");
    expect(screen.queryByText("系统故障")).not.toBeInTheDocument();
  });
});

describe("vault automatic locking", () => {
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

  it("locks after five idle minutes and activity resets the timer", () => {
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
