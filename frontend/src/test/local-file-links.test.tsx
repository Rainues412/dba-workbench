import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LocalFileLinks } from "../components/LocalFileLinks";
import { setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });

const script = { id: 1, revision: 1, file_path: "D:\\Database\\巡检 脚本.sql" };
const config = { pathField: "file_path", openMode: "edit" as const, openLabel: "打开脚本" };

describe("local shortcuts", () => {
  it("opens a script in an editor through the authenticated API", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetch);
    setCsrfToken("test-csrf-token");
    render(<LocalFileLinks row={script} label="巡检脚本" config={config} disabled={false} onNotice={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "打开脚本：巡检脚本" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [path, options] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/launcher/path");
    expect(JSON.parse(String(options.body))).toEqual({ path: script.file_path, mode: "edit" });
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("test-csrf-token");
  });

  it("locates the containing folder without running the script", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetch);
    const onNotice = vi.fn();
    render(<LocalFileLinks row={script} label="巡检脚本" config={config} disabled={false} onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "打开所在文件夹：巡检脚本" }));
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("已打开所在文件夹"));
    expect(JSON.parse(String((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body)).mode).toBe("folder");
  });

  it("copies the original path", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const onNotice = vi.fn();
    render(<LocalFileLinks row={script} label="巡检脚本" config={config} disabled={false} onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "复制路径：巡检脚本" }));
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("路径已复制"));
    expect(writeText).toHaveBeenCalledWith(script.file_path);
  });

  it("shows the real permission error and does not fall back to executing a file", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ error: { message: "路径超出允许目录" } }), { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    const onNotice = vi.fn();
    render(<LocalFileLinks row={script} label="巡检脚本" config={config} disabled={false} onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "打开脚本：巡检脚本" }));
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("路径超出允许目录"));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("opens resource web shortcuts in a separate tab", () => {
    render(<LocalFileLinks row={{ id: 1, revision: 1, url: "https://example.com/docs" }} label="数据库文档" config={{ pathField: "path", urlField: "url", openMode: "open", openLabel: "打开资源" }} disabled={false} onNotice={vi.fn()} />);
    const link = screen.getByRole("link", { name: "打开网址：数据库文档" });
    expect(link).toHaveAttribute("href", "https://example.com/docs");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not create executable links for unsupported URL schemes", () => {
    render(<LocalFileLinks row={{ id: 1, revision: 1, url: "javascript:alert(1)" }} label="无效链接" config={{ pathField: "path", urlField: "url", openMode: "open", openLabel: "打开资源" }} disabled={false} onNotice={vi.fn()} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("网址无效，仅支持 http/https")).toBeInTheDocument();
  });
});
