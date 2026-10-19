import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LegacyTaskArchive } from "../components/LegacyTaskArchive";
import { setCsrfToken } from "../api/client";

const KEY = "wb_dba_workbench_tasks_archive";
const entry = { id: "old-1", title: "旧任务", notes: "说明", priority: "P0", completedAt: "2025-01-01T00:00:00Z" };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); localStorage.clear(); });

function show(items: unknown = [entry]) {
  const raw = JSON.stringify(items);
  localStorage.setItem(KEY, raw);
  const onImported = vi.fn(async () => undefined);
  render(<LegacyTaskArchive onImported={onImported} />);
  fireEvent.click(screen.getByRole("button", { name: "旧任务归档" }));
  return { raw, onImported };
}

describe("explicit legacy task archive migration", () => {
  it("does not migrate until explicitly confirmed and never clears source data", async () => {
    const fetch = vi.fn(async () => response({ imported: 1, skipped: 0 }));
    vi.stubGlobal("fetch", fetch);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    setCsrfToken("archive-csrf");
    const { raw, onImported } = show();
    expect(screen.getByText("发现 1 条旧归档")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "追加导入已完成任务" }));
    expect(fetch).not.toHaveBeenCalled();
    expect(onImported).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "追加导入已完成任务" }));
    await screen.findByText(/已导入 1 条，跳过已迁移 0 条/);
    await waitFor(() => expect(onImported).toHaveBeenCalledTimes(1));
    const [path, options] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/tasks/legacy-archive");
    expect(JSON.parse(String(options.body))).toEqual({ items: [entry] });
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("archive-csrf");
    expect(localStorage.getItem(KEY)).toBe(raw);
  });

  it("shows retry skips while retaining the untouched browser archive", async () => {
    const fetch = vi.fn(async () => response({ imported: 0, skipped: 1 }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { raw } = show();
    fireEvent.click(screen.getByRole("button", { name: "追加导入已完成任务" }));
    await screen.findByText(/已导入 0 条，跳过已迁移 1 条/);
    expect(localStorage.getItem(KEY)).toBe(raw);
  });

  it("reports batch failures and completed batch counts without clearing original data", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ imported: 200, skipped: 0 })).mockResolvedValueOnce(response({ error: { message: "日期格式错误" } }, 422));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { raw, onImported } = show(Array.from({ length: 201 }, (_, index) => ({ ...entry, id: index, title: `任务 ${index}` })));
    fireEvent.click(screen.getByRole("button", { name: "追加导入已完成任务" }));
    await screen.findByText(/本次已导入 200 条，后续失败：日期格式错误/);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String((fetch.mock.calls[0] as [string, RequestInit])[1].body)).items).toHaveLength(200);
    expect(JSON.parse(String((fetch.mock.calls[1] as [string, RequestInit])[1].body)).items).toHaveLength(1);
    expect(localStorage.getItem(KEY)).toBe(raw);
    await waitFor(() => expect(onImported).toHaveBeenCalledTimes(1));
  });

  it("rejects malformed browser source without mutating or importing it", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { raw } = show({ bad: "source" });
    expect(screen.getByRole("status")).toHaveTextContent("无法读取旧归档，源数据未修改");
    expect(screen.getByRole("button", { name: "追加导入已完成任务" })).toBeDisabled();
    expect(localStorage.getItem(KEY)).toBe(raw);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([{ completedAt: 123 }, { priority: { invalid: true } }, { notes: [] }])("rejects malformed optional archive fields without crashing the preview: %j", (invalid) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const raw = JSON.stringify([{ ...entry, ...invalid }]);
    localStorage.setItem(KEY, raw);
    render(<LegacyTaskArchive onImported={async () => undefined} />);
    expect(() => fireEvent.click(screen.getByRole("button", { name: "旧任务归档" }))).not.toThrow();
    expect(screen.getByRole("status")).toHaveTextContent("源数据未修改");
    expect(screen.getByRole("button", { name: "追加导入已完成任务" })).toBeDisabled();
    expect(localStorage.getItem(KEY)).toBe(raw);
    expect(fetch).not.toHaveBeenCalled();
  });
});
