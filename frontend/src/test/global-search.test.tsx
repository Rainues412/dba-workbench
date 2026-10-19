import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalSearch } from "../components/GlobalSearch";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function Location() { const location = useLocation(); return <output aria-label="当前位置">{location.pathname}{location.search}</output>; }
function mount() { render(<MemoryRouter><GlobalSearch /><Location /></MemoryRouter>); }
function search(value: string) {
  fireEvent.click(screen.getByRole("button", { name: "全局搜索（Ctrl+K）" }));
  fireEvent.change(screen.getByRole("textbox", { name: "跨模块搜索关键词" }), { target: { value } });
}
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe("global search", () => {
  it("opens with Ctrl+K, focuses the input and restores focus after Escape", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); mount();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("textbox")).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全局搜索（Ctrl+K）" })).toHaveFocus();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("searches across non-secret modules and jumps to the exact record", async () => {
    const fetch = vi.fn(async () => response({ scripts: [{ id: 21, title: "MySQL 巡检" }], customers: [{ id: 3, name: "客户 A" }], passwords: [{ id: 1, title: "不应显示" }] }));
    vi.stubGlobal("fetch", fetch); mount(); search("MySQL");
    const result = await screen.findByRole("button", { name: "MySQL 巡检" });
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe("/api/search/?q=MySQL&limit=10");
    expect(screen.getByRole("button", { name: "客户 A" })).toBeInTheDocument();
    expect(screen.queryByText("不应显示")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "ArrowDown" });
    expect(result).toHaveFocus();
    fireEvent.click(result);
    expect(screen.getByLabelText("当前位置")).toHaveTextContent("/scripts?record=21");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("ignores a stale response when the query changes", async () => {
    let finishOld: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { finishOld = resolve; })).mockResolvedValue(response({ articles: [{ id: 7, title: "新的结果" }] }));
    vi.stubGlobal("fetch", fetch); mount(); search("旧");
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "新" } });
    await screen.findByRole("button", { name: "新的结果" });
    finishOld(response({ articles: [{ id: 1, title: "过期结果" }] }));
    await waitFor(() => expect(screen.getByRole("button", { name: "新的结果" })).toBeInTheDocument());
    expect(screen.queryByText("过期结果")).not.toBeInTheDocument();
  });

  it("shows API failures and empty results without inventing records", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ error: { message: "暂不可用" } }, 503)).mockResolvedValue(response({})));
    mount(); search("失败");
    expect(await screen.findByRole("alert")).toHaveTextContent("暂不可用");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "无结果" } });
    expect(await screen.findByText("没有匹配记录")).toBeInTheDocument();
  });
});
