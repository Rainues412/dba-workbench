import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalSearch } from "../components/GlobalSearch";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function Location() { const location = useLocation(); return <output aria-label="当前位置">{location.pathname}{location.search}</output>; }
function mount() { render(<MemoryRouter><GlobalSearch /><Location /></MemoryRouter>); }
function search(value: string) {
  const input = screen.getByRole("combobox", { name: "跨模块搜索关键词" });
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value } });
}
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe("global search", () => {
  it("focuses the inline input with Ctrl+K and closes the dropdown with Escape", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ scripts: [{ id: 1, title: "巡检" }] })));
    mount();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("combobox")).toHaveFocus();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "巡检" } });
    await screen.findByRole("listbox");
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("searches all non-secret modules inline and jumps to the exact record", async () => {
    const fetch = vi.fn(async () => response({ scripts: [{ id: 21, title: "MySQL 巡检" }], customers: [{ id: 3, name: "客户 A" }], tasks: [{ id: 8, title: "不应参与搜索的任务" }], passwords: [{ id: 1, title: "不应显示" }] }));
    vi.stubGlobal("fetch", fetch); mount(); search("MySQL");
    expect(await screen.findByRole("option", { name: /MySQL 巡检/ })).toBeInTheDocument();
    const resultTitle = screen.getByRole("option", { name: /MySQL 巡检/ }).querySelector(".global-search-result-title");
    expect(resultTitle).toHaveAttribute("title", "MySQL 巡检");
    expect(resultTitle?.querySelector("mark")).toHaveTextContent("MySQL");
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe("/api/search/?q=MySQL&limit=0");
    expect(screen.getByRole("option", { name: /客户 A/ })).toBeInTheDocument();
    expect(screen.queryByText("不应参与搜索的任务")).not.toBeInTheDocument();
    expect(screen.queryByText("不应显示")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "ArrowDown" });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    expect(screen.getByLabelText("当前位置")).toHaveTextContent("/scripts?preview=21");
  });

  it("keeps all matches in one scrollable list rather than truncating to five", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ scripts: Array.from({ length: 7 }, (_, index) => ({ id: index + 1, title: `结果 ${index + 1}` })) })));
    mount(); search("结果");
    expect(await screen.findAllByRole("option")).toHaveLength(7);
    expect(screen.getByRole("listbox")).toHaveClass("global-search-dropdown");
  });

  it("ignores a stale response when the query changes", async () => {
    let finishOld: (value: Response) => void = () => undefined;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { finishOld = resolve; })).mockResolvedValue(response({ articles: [{ id: 7, title: "新的结果" }] }));
    vi.stubGlobal("fetch", fetch); mount(); search("旧");
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "新" } });
    await screen.findByRole("option", { name: /新的结果/ });
    finishOld(response({ articles: [{ id: 1, title: "过期结果" }] }));
    await waitFor(() => expect(screen.getByRole("option", { name: /新的结果/ })).toBeInTheDocument());
    expect(screen.queryByText("过期结果")).not.toBeInTheDocument();
  });

  it("shows API failures and empty results without inventing records", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ error: { message: "暂不可用" } }, 503)).mockResolvedValue(response({})));
    mount(); search("失败");
    expect(await screen.findByRole("alert")).toHaveTextContent("暂不可用");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "无结果" } });
    expect(await screen.findByText("没有匹配记录")).toBeInTheDocument();
  });

  it.each(["articles", "resources", "customers"])("uses the correct read or edit target for %s", async (module) => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ [module]: [{ id: 9, title: "目标文件" }] })));
    mount(); search("目标");
    fireEvent.click(await screen.findByRole("option", { name: /目标文件/ }));
    expect(screen.getByLabelText("当前位置")).toHaveTextContent(`/${module}?${module === "articles" ? "preview" : "record"}=9`);
  });
});
