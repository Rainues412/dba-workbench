import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EntityDetails } from "../components/EntityDetails";
import { Entity, setCsrfToken } from "../api/client";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); setCsrfToken(null); });

function show(module: string, item: Entity) {
  const onRefresh = vi.fn(async () => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<MemoryRouter><QueryClientProvider client={client}><EntityDetails module={module} item={item} onRefresh={onRefresh} /></QueryClientProvider></MemoryRouter>);
  return onRefresh;
}
const script = { id: 7, revision: 9, version: 4, versions: [{ version: 3, created_at: "2026-10-18" }] };
const customer = { id: 8, revision: 1, contacts: [{ id: 12, name: "张三", role: "DBA", phone: "100", wechat: "wx", notes: "联系人备注" }], communications: [{ id: 15, date: "2026-10-18", content: "例行回访", follow_up: "下周跟进" }], tasks: [{ id: 24, title: "客户巡检", status: "待处理", priority: "高" }] };

describe("script history details", () => {
  it("reads selected history and restores with the current revision and CSRF token", async () => {
    const fetch = vi.fn(async (path: string) => Response.json(path.endsWith("/versions/3") ? { content: "SELECT 3;" } : { ok: true }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    setCsrfToken("history-csrf");
    const onRefresh = show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    expect(await screen.findByLabelText("历史正文")).toHaveValue("SELECT 3;");
    expect(screen.getByLabelText("历史正文")).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "恢复此版本为当前正文" }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    const [path, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(path).toBe("/api/scripts/7");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ content: "SELECT 3;" });
    expect(new Headers(init.headers).get("If-Match")).toBe("9");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("history-csrf");
  });

  it("shows history errors without enabling restore and permits retry", async () => {
    let failed = true;
    vi.stubGlobal("fetch", vi.fn(async () => failed ? Response.json({}, { status: 500 }) : Response.json({ content: "retried content" })));
    show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    await screen.findByText("历史版本加载失败");
    expect(screen.queryByRole("button", { name: "恢复此版本为当前正文" })).not.toBeInTheDocument();
    failed = false;
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByLabelText("历史正文")).toHaveValue("retried content");
  });

  it("does not retry an optimistic conflict with an unverified revision", async () => {
    const fetch = vi.fn(async (path: string) => path.endsWith("/versions/3") ? Response.json({ content: "SELECT 3;" }) : Response.json({ error: { message: "版本冲突" } }, { status: 409 }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onRefresh = show("scripts", script);
    fireEvent.change(screen.getByLabelText("查看历史版本"), { target: { value: "3" } });
    await screen.findByLabelText("历史正文");
    fireEvent.click(screen.getByRole("button", { name: "恢复此版本为当前正文" }));
    await screen.findByText("版本冲突");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});

describe("customer related details", () => {
  it("shows the linked task and creates a contact with all entered fields", async () => {
    const fetch = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    const onRefresh = show("customers", customer);
    expect(screen.getByRole("link", { name: "客户巡检" })).toHaveAttribute("href", "/tasks?record=24");
    expect(screen.getByText("下周跟进", { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新增联系人" }));
    for (const [label, value] of [["姓名", "李四"], ["角色", "主管"], ["电话", "200"], ["微信", "wx2"], ["备注", "新联系人"]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.submit(screen.getByLabelText("姓名").closest("form")!);
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/customers/8/contacts");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ name: "李四", role: "主管", phone: "200", wechat: "wx2", notes: "新联系人" });
  });

  it("updates and deletes the selected contact using contact-specific endpoints", async () => {
    const fetch = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onRefresh = show("customers", customer);
    fireEvent.click(screen.getByRole("button", { name: "编辑联系人" }));
    expect(screen.getByLabelText("姓名")).toHaveValue("张三");
    fireEvent.change(screen.getByLabelText("电话"), { target: { value: "300" } });
    fireEvent.submit(screen.getByLabelText("姓名").closest("form")!);
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "删除联系人" }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(2));
    const calls = fetch.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls.map(([path, init]) => [path, init.method])).toEqual([["/api/customers/contacts/12", "PUT"], ["/api/customers/contacts/12", "DELETE"]]);
    expect(JSON.parse(String(calls[0][1].body)).phone).toBe("300");
  });

  it("creates and deletes communication records", async () => {
    const fetch = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onRefresh = show("customers", customer);
    fireEvent.click(screen.getByRole("button", { name: "新增沟通记录" }));
    fireEvent.change(screen.getByLabelText("日期"), { target: { value: "2026-10-19" } });
    fireEvent.change(screen.getByLabelText("沟通内容"), { target: { value: "需求确认" } });
    fireEvent.change(screen.getByLabelText("后续跟进"), { target: { value: "次日回访" } });
    fireEvent.submit(screen.getByLabelText("日期").closest("form")!);
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "删除沟通记录" }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(2));
    const calls = fetch.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls.map(([path, init]) => [path, init.method])).toEqual([["/api/customers/8/communications", "POST"], ["/api/customers/communications/15", "DELETE"]]);
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ date: "2026-10-19", content: "需求确认", follow_up: "次日回访" });
  });
});
