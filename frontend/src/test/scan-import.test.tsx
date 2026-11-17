import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScanImport } from "../components/ScanImport";
import { setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const proposals = [
  { kind: "script", name: "巡检一", path: "D:\\Database\\巡检一.sql", db_type: "MySQL" },
  { kind: "script", name: "巡检二", path: "D:\\Database\\巡检二.sql", db_type: "Oracle" },
  { kind: "article", name: "其他模块文档", path: "D:\\Database\\其他模块文档.md" },
];
const alreadyIndexed = { article: 272, script: 12, resource: 0 };
function open() { fireEvent.click(screen.getByRole("button", { name: "目录批量导入" })); }
function scan() {
  fireEvent.change(screen.getByRole("textbox", { name: "扫描目录" }), { target: { value: "D:\\Database" } });
  fireEvent.click(screen.getByRole("button", { name: "扫描预览" }));
}

describe("directory import", () => {
  it("requires an explicit directory and does not scan automatically", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); render(<ScanImport module="scripts" />); open();
    const directory = screen.getByRole("textbox");
    expect(directory).toHaveFocus();
    expect(directory).toHaveAttribute("placeholder", "输入文件夹路径");
    expect(screen.queryByText("首次使用请选择目录完成授权。", { exact: false })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "扫描预览" })).toBeDisabled();
    expect(screen.getAllByRole("button", { name: /^关闭/ })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^导入所选/ })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("previews only the current module and imports only checked files with CSRF", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ items: proposals, already_indexed: alreadyIndexed })).mockResolvedValueOnce(response({ imported: { script: 1, skipped: 0 } }));
    vi.stubGlobal("fetch", fetch); setCsrfToken("scan-csrf"); const onImported = vi.fn();
    render(<ScanImport module="scripts" onImported={onImported} />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：巡检一.sql" });
    const selectAll = screen.getByRole("checkbox", { name: "全选导入文件" });
    expect(selectAll).toBeChecked();
    expect(screen.getByRole("status")).toHaveTextContent("2 个脚本可导入");
    expect(screen.getByRole("status")).toHaveTextContent("已入库 12 个脚本");
    expect(screen.getByRole("status")).toHaveTextContent("知识库导入 1 项");
    expect(screen.queryByRole("checkbox", { name: "导入：其他模块文档.md" })).not.toBeInTheDocument();
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({ paths: ["D:\\Database"] });
    fireEvent.click(screen.getByRole("checkbox", { name: "导入：巡检二.sql" }));
    expect(selectAll).toBePartiallyChecked();
    fireEvent.click(screen.getByRole("button", { name: "导入所选（1）" }));
    await screen.findByText("已导入 1 条，跳过重复 0 条。");
    expect(fetch.mock.calls[1][0]).toBe("/api/scan/commit");
    expect(JSON.parse(String(fetch.mock.calls[1][1].body))).toEqual({ items: [proposals[0]] });
    expect(new Headers(fetch.mock.calls[1][1].headers).get("X-CSRF-Token")).toBe("scan-csrf");
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("已入库 13 个脚本");
  });

  it("explains a forbidden scan without modifying local permissions", async () => {
    const fetch = vi.fn(async () => response({ detail: "扫描未开启" }, 403)); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="articles" />); open(); scan();
    expect(await screen.findByRole("alert")).toHaveTextContent("可通过「选择目录」授权后重试");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /^导入所选/ })).not.toBeInTheDocument();
  });

  it("uses the native directory picker and handles cancellation", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ ok: false, path: "", reason: "cancelled" })).mockResolvedValueOnce(response({ ok: true, path: "D:\\Database\\MySQL" })); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="resources" />); open();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "D:\\Database" } });
    fireEvent.click(screen.getByRole("button", { name: "选择目录" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "选择目录" })).toBeEnabled());
    expect(screen.getByRole("textbox")).toHaveValue("D:\\Database");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择目录" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("D:\\Database\\MySQL"));
    expect(fetch.mock.calls.every(([url]) => url === "/api/launcher/pick-folder")).toBe(true);
  });

  it("discards preview selection when its directory changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ proposed: 3, items: proposals })));
    render(<ScanImport module="scripts" />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：巡检一.sql" });
    expect(screen.getByRole("button", { name: "重新扫描" })).toBeEnabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "D:\\Database\\Other" } });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^导入所选/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "扫描预览" })).toBeEnabled();
  });

  it("aborts a preview when dismissed and restores trigger focus", async () => {
    let finish!: (value: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })); vi.stubGlobal("fetch", fetch);
    render(<ScanImport module="scripts" />); open(); scan();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "目录批量导入" })).toHaveFocus();
    expect((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].signal?.aborted).toBe(true);
    open();
    await act(async () => { finish(response({ items: proposals })); });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "扫描预览" })).toBeEnabled();
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

  it.each([
    { count: 272, message: "272 个文档均已入库" },
    { count: 0, message: "扫描范围内没有支持的文档" },
    { count: undefined, message: "没有可导入的文档" },
  ])("distinguishes an empty preview when $count document paths are indexed", async ({ count, message }) => {
    const items = proposals.filter((item) => item.kind === "script");
    const result = count === undefined ? { items } : { items, already_indexed: { article: count, script: 12, resource: 0 } };
    vi.stubGlobal("fetch", vi.fn(async () => response(result)));
    render(<ScanImport module="articles" />); open(); scan();
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(message);
    expect(status).toHaveTextContent("同一目录可在脚本库导入 2 项。");
    expect(screen.queryByRole("button", { name: /^导入所选/ })).not.toBeInTheDocument();
  });

  it("does not encourage reimport when commit succeeded but list refresh failed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ proposed: 3, items: proposals })).mockResolvedValueOnce(response({ imported: { article: 0, skipped: 1 } })));
    render(<ScanImport module="articles" onImported={async () => { throw new Error("refresh failed"); }} />); open(); scan();
    await screen.findByRole("checkbox", { name: "导入：其他模块文档.md" });
    fireEvent.click(screen.getByRole("button", { name: "导入所选（1）" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("导入已成功，但列表刷新失败");
    expect(screen.getByRole("status")).toHaveTextContent("跳过重复 1 条");
    expect(screen.queryByRole("button", { name: /^导入所选/ })).not.toBeInTheDocument();
  });
});
