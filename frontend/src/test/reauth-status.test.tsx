import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useReauthStatus } from "../vault/useReauthStatus";

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("sensitive-operation expiry", () => {
  it("counts down and expires without another render or interaction", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-27T08:00:00Z"));
    const { result } = renderHook(() => useReauthStatus("2026-10-27T08:00:02Z"));
    expect(result.current.remainingSeconds).toBe(2);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.remainingSeconds).toBe(1);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.reauthenticated).toBe(false);
    expect(result.current.expired).toBe(true);
    expect(result.current.remainingSeconds).toBe(0);
  });

  it("rechecks wall-clock time after suspension and accepts a renewed deadline", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-27T08:00:00Z"));
    const { result, rerender } = renderHook(({ until }) => useReauthStatus(until), { initialProps: { until: "2026-10-27T08:30:00Z" } });
    vi.setSystemTime(new Date("2026-10-27T09:00:00Z"));
    expect(result.current.isCurrent()).toBe(false);
    act(() => window.dispatchEvent(new Event("focus")));
    expect(result.current.expired).toBe(true);
    rerender({ until: "2026-10-27T09:30:00Z" });
    expect(result.current.reauthenticated).toBe(true);
    expect(result.current.remainingSeconds).toBe(1800);
    vi.setSystemTime(new Date("2026-10-27T10:00:00Z"));
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(result.current.expired).toBe(true);
  });

  it("treats missing and invalid deadlines as unverified", () => {
    const { result, rerender } = renderHook(({ until }) => useReauthStatus(until), { initialProps: { until: "" } });
    expect(result.current.reauthenticated).toBe(false);
    expect(result.current.expired).toBe(false);
    rerender({ until: "invalid date" });
    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.isCurrent()).toBe(false);
  });
});
