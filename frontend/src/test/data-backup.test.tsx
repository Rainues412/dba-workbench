import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataBackup } from "../components/DataBackup";
import { setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><DataBackup /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: "普通数据备份" }));
  return invalidate;
}

function select(value: string) {
  fireEvent.change(screen.getByLabelText("选择备份文件"), { target: { files: [{ text: async () => value }] } });
}

describe("ordinary module backup", () => {
  it("validates JSON and does not send unrecognized or malformed backups", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    show();
    select("not-json");
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "确认追加导入" })).toBeDisabled();
    select(JSON.stringify({ vault_items: [] }));
    await screen.findByText(/未识别到普通模块备份/);
    select(JSON.stringify({ scripts: [null] }));
    await screen.findByText("脚本数据必须是记录数组");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires append confirmation, uses CSRF, displays counts and refreshes module caches", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, imported: { scripts: 1 }, errors: [] })));
    vi.stubGlobal("fetch", fetch);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    setCsrfToken("backup-csrf");
    const invalidate = show();
    select(JSON.stringify({ scripts: [{ title: "备份脚本" }] }));
    await screen.findByText("待追加：脚本 1 条");
    fireEvent.click(screen.getByRole("button", { name: "确认追加导入" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("重复导入将产生重复记录"));
    expect(fetch).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "确认追加导入" }));
    await screen.findByText("追加导入完成：脚本 1 条。现有记录保持不变。");
    const [path, options] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/export/import");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("backup-csrf");
    expect(JSON.parse(String(options.body))).toEqual({ data: { scripts: [{ title: "备份脚本" }] } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["scripts"] });
    expect(screen.getByRole("button", { name: "确认追加导入" })).toBeDisabled();
  });

  it("shows rollback errors without a success notification", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { message: "导入失败，未写入任何记录：scripts 第 1 条" } }), { status: 400 })));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const invalidate = show();
    select(JSON.stringify({ scripts: [{ title: "a" }] }));
    await screen.findByText("待追加：脚本 1 条");
    fireEvent.click(screen.getByRole("button", { name: "确认追加导入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("未写入任何记录");
    expect(screen.queryByText(/追加导入完成/)).not.toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("downloads an ordinary JSON backup without including vault data", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ scripts: [], exported_at: "2026-10-19" })));
    vi.stubGlobal("fetch", fetch);
    const createObjectURL = vi.fn(() => "blob:backup");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    show();
    fireEvent.click(screen.getByRole("button", { name: "导出 JSON 备份" }));
    await screen.findByText("普通模块备份已下载，包含数据库中的正文，不打包原路径文件或保险箱。");
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe("/api/export/all");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
  });
});
