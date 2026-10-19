import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScanImport } from "../components/ScanImport";
import { setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const proposals = [
  { kind: "script", name: "巡检一", path: "D:\\Database\\a.sql", db_type: "MySQL" },
  { kind: "script", name: "巡检二", path: "D:\\Database\\b.sql", db_type: "Oracle" },
  { kind: "article", name: "其他模块文档", path: "D:\\Database\\c.md" },
];
function open() { fireEvent.click(screen.getByRole("button", { name: "目录批量导入" })); }
function scan() {
  fireEvent.change(screen.getByRole("textbox", { name: "扫描目录" }), { target: { value: "D:\\Database" } });
  fireEvent.click(screen.getByRole("button", { name: "扫描预览" }));
}

describe("directory import", () => {
  it("requires an explicit directory and does not scan automatically", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); render(<ScanImport module="scripts" />); open();
    expect(screen.getByRole("textbox")).toHaveFocus();
    expect(screen.getByRole("button", { name: "扫描预览" })).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("previews only the current module and imports only checked files with CSRF", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ proposed: 3, items: proposals })).mockResolvedValueOnce(response({ imported: { script: 1, skipped: 0 } }));
    vi.stubGlobal("fetch", fetch); setCsrfToken("scan-csrf"); const onImported = vi.fn();
    render(<ScanImport module="scripts" onImported={onImported} />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：巡检一" });
    expect(screen.queryByText("其他模块文档")).not.toBeInTheDocument();
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({ paths: ["D:\\Database"] });
    fireEvent.click(screen.getByRole("checkbox", { name: "导入：巡检二" }));
    fireEvent.click(screen.getByRole("button", { name: "导入所选（1）" }));
    await screen.findByText("已导入 1 条，跳过重复 0 条。");
    expect(fetch.mock.calls[1][0]).toBe("/api/scan/commit");
    expect(JSON.parse(String(fetch.mock.calls[1][1].body))).toEqual({ items: [proposals[0]] });
    expect(new Headers(fetch.mock.calls[1][1].headers).get("X-CSRF-Token")).toBe("scan-csrf");
    expect(onImported).toHaveBeenCalledTimes(1);
  });

  it("explains a forbidden scan without modifying local permissions", async () => {
    const fetch = vi.fn(async () => response({ detail: "扫描未开启" }, 403)); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="articles" />); open(); scan();
    expect(await screen.findByRole("alert")).toHaveTextContent("不会自动扩大权限");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "导入所选（0）" })).toBeDisabled();
  });

  it("uses the native directory picker and handles cancellation", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ ok: false, path: "" })).mockResolvedValueOnce(response({ ok: true, path: "D:\\Database\\MySQL" })); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="resources" />); open();
    fireEvent.click(screen.getByRole("button", { name: "选择目录" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "选择目录" })).toBeEnabled());
    expect(screen.getByRole("textbox")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "选择目录" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("D:\\Database\\MySQL"));
    expect(fetch.mock.calls.every(([url]) => url === "/api/launcher/pick-folder")).toBe(true);
  });

  it("discards preview selection when its directory changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ proposed: 3, items: proposals })));
    render(<ScanImport module="scripts" />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：巡检一" });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "D:\\Database\\Other" } });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入所选（0）" })).toBeDisabled();
  });

  it("aborts a preview when dismissed and restores trigger focus", async () => {
    const fetch = vi.fn(() => new Promise<Response>(() => undefined)); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="scripts" />); open(); scan();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "目录批量导入" })).toHaveFocus();
    expect((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].signal?.aborted).toBe(true);
  });

  it("keeps manual directory entry available if the picker is forbidden", async () => {
    const fetch = vi.fn(async () => response({ detail: "pick-folder 未开启" }, 403)); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="articles" />); open();
    fireEvent.click(screen.getByRole("button", { name: "选择目录" }));
    await screen.findByRole("alert");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "D:\\Note" } });
    expect(screen.getByRole("button", { name: "扫描预览" })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not offer import when only other module files were found", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ proposed: 3, items: proposals })));
    render(<ScanImport module="resources" />); open(); scan();
    expect(await screen.findByRole("status")).toHaveTextContent("其中 0 个资源");
    expect(screen.getByRole("button", { name: "导入所选（0）" })).toBeDisabled();
  });

  it("does not encourage reimport when commit succeeded but list refresh failed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ proposed: 3, items: proposals })).mockResolvedValueOnce(response({ imported: { article: 0, skipped: 1 } })));
    render(<ScanImport module="articles" onImported={async () => { throw new Error("refresh failed"); }} />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：其他模块文档" });
    fireEvent.click(screen.getByRole("button", { name: "导入所选（1）" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("导入已成功，但列表刷新失败");
    expect(screen.getByRole("status")).toHaveTextContent("跳过重复 1 条");
    expect(screen.getByRole("button", { name: "导入所选（0）" })).toBeDisabled();
  });
});
