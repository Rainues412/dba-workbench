import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../pages/Dashboard";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ session: { user: { username: "dba-owner" } } }),
}));

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("greets the signed-in user and updates across local time periods", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 10, 18, 4, 59));
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, gcTime: 0 } } });
  client.setQueryData(["dashboard", "stats"], { script_count: 0, article_count: 0, task_total: 0, task_pending: 0, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 });
  client.setQueryData(["dashboard", "tasks"], []);
  client.setQueryData(["dashboard", "database-distribution"], []);
  render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

  expect(screen.getByRole("heading", { level: 1, name: "晚上好，dba-owner" })).toBeInTheDocument();
  for (const [hour, greeting] of [[5, "早上好"], [11, "中午好"], [13, "下午好"], [18, "晚上好"]] as const) {
    vi.setSystemTime(new Date(2026, 10, 18, hour - 1, 59));
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(screen.getByRole("heading", { level: 1, name: `${greeting}，dba-owner` })).toBeInTheDocument();
  }
  expect(screen.queryByRole("heading", { name: "常用入口" })).not.toBeInTheDocument();
});

describe("dashboard task queue", () => {
  it("keeps the greeting visible and reveals each section independently, including failure and retry", async () => {
    const pending = new Map<string, (response: Response) => void>();
    vi.stubGlobal("fetch", vi.fn((path: string) => new Promise<Response>((resolve) => pending.set(path, resolve))));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("dba-owner");
    expect(screen.getByRole("status", { name: "正在加载近期任务" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "正在加载数据库分布" })).toBeInTheDocument();
    await act(async () => pending.get("/api/dashboard/stats")!(Response.json({ script_count: 128, article_count: 0, task_pending: 0, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 })));
    expect(screen.getByRole("region", { name: "数据摘要" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status", { name: "正在加载近期任务" })).toBeInTheDocument();
    await act(async () => pending.get("/api/dashboard/database-distribution")!(Response.json({}, { status: 500 })));
    expect(await screen.findByText("数据库分布加载失败")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据摘要" })).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByRole("status", { name: "正在加载数据库分布" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /脚本资产/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByRole("status", { name: "正在加载数据库分布" })).toBeInTheDocument());
    await act(async () => {
      pending.get("/api/dashboard/database-distribution")!(Response.json([{ name: "MongoDB", count: 2 }]));
      pending.get("/api/dashboard/recent-tasks")!(Response.json([]));
    });
    await waitFor(() => expect(screen.queryByRole("status", { name: "正在加载数据库分布" })).not.toBeInTheDocument());
    expect(screen.getByText("MongoDB")).toBeInTheDocument();
    expect(await screen.findByText("任务队列已清空")).toBeInTheDocument();
  });

  it("starts cached numbers and bars together from zero without a skeleton", () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, gcTime: 0 } } });
    client.setQueryData(["dashboard", "stats"], { script_count: 128, article_count: 0, task_pending: 0, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 });
    client.setQueryData(["dashboard", "tasks"], []);
    client.setQueryData(["dashboard", "database-distribution"], [{ name: "MongoDB", count: 2 }]);
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);
    const card = screen.getByRole("link", { name: /脚本资产/ });
    expect(card.querySelector(".dashboard-number > [aria-hidden=true]")).toHaveTextContent("0");
    expect(document.querySelector(".progress-track > span")).toHaveStyle({ transform: "scaleX(0)" });
    expect(document.querySelector(".skeleton-block")).toBeNull();
  });

  it("renders MongoDB as its own database distribution item", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/dashboard/stats") return Response.json({ script_count: 1, article_count: 1, task_total: 0, task_pending: 0, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 });
      if (path === "/api/dashboard/recent-tasks") return Response.json([]);
      if (path === "/api/dashboard/database-distribution") return Response.json([{ name: "MongoDB", count: 2 }]);
      throw new Error(`Unexpected request: ${path}`);
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("MongoDB")).toBeInTheDocument();
  });

  it("shows overdue tasks and supports quick completion", async () => {
    let completed = false;
    const writes: Array<{ path: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        writes.push({ path, init }); completed = true;
        return Response.json({ id: 7, revision: 4, title: "处理逾期任务", status: "已完成" });
      }
      if (path === "/api/dashboard/stats") return Response.json({ script_count: 0, article_count: 0, task_total: 1, task_pending: completed ? 0 : 1, task_overdue: completed ? 0 : 1, customer_count: 0, resource_count: 0, password_count: 0 });
      if (path === "/api/dashboard/recent-tasks") return Response.json(completed ? [] : [{ id: 7, revision: 3, title: "处理逾期任务", priority: "高", status: "待处理", due_date: "2020-01-01", is_overdue: 1 }]);
      if (path === "/api/dashboard/database-distribution") return Response.json([]);
      throw new Error(`Unexpected request: ${path}`);
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    expect(await screen.findByRole("link", { name: "1 项逾期" })).toBeInTheDocument();
    expect(screen.getByText("已逾期")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "完成任务：处理逾期任务" });
    vi.useFakeTimers();
    button.focus();
    fireEvent.click(button);
    fireEvent.click(button);
    expect(button).toHaveAttribute("data-phase", "pending");
    await act(async () => { await vi.advanceTimersByTimeAsync(240); });
    expect(button).toHaveAttribute("data-phase", "success");
    await act(async () => { await client.invalidateQueries({ queryKey: ["dashboard", "tasks"] }); await vi.advanceTimersByTimeAsync(10); });
    expect(button).toBeInTheDocument();

    expect(writes).toHaveLength(1);
    expect(writes[0].path).toBe("/api/tasks/7");
    expect(new Headers(writes[0].init?.headers).get("If-Match")).toBe("3");
    expect(JSON.parse(String(writes[0].init?.body))).toEqual({ status: "已完成" });
    await act(async () => { await vi.advanceTimersByTimeAsync(550); });
    expect(screen.getByText("任务队列已清空")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看全部" })).toHaveFocus();
  });

  it("shows each real task status independently of overdue warnings", async () => {
    const taskRows = [
      { id: 1, status: "待处理", is_overdue: 0 },
      { id: 2, status: "进行中", is_overdue: 0 },
      { id: 3, status: "待处理", is_overdue: 1 },
      { id: 4, status: "进行中", is_overdue: 1 },
    ].map((task) => ({ ...task, revision: 1, title: `状态任务 ${task.id}`, priority: "中" }));
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/dashboard/stats") return Response.json({ script_count: 0, article_count: 0, task_total: 4, task_pending: 4, task_overdue: 2, customer_count: 0, resource_count: 0, password_count: 0 });
      if (path === "/api/dashboard/recent-tasks") return Response.json(taskRows);
      if (path === "/api/dashboard/database-distribution") return Response.json([]);
      throw new Error(`Unexpected request: ${path}`);
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    await screen.findByRole("list", { name: "未完成任务列表" });
    for (const task of taskRows) {
      const row = within(screen.getByText(task.title).closest("li")!);
      expect(row.getByText(task.status)).toBeInTheDocument();
      expect(row.queryByText("已逾期") !== null).toBe(Boolean(task.is_overdue));
      if (task.status === "进行中") expect(row.getByText(task.status)).toHaveClass("status-info");
    }
  });

  it("keeps more than six unfinished tasks in an internally scrollable list", async () => {
    const taskRows = Array.from({ length: 8 }, (_, index) => ({
      id: index + 1, revision: 1, title: `任务 ${index + 1}`, priority: "低",
      status: "待处理", due_date: "2099-01-01", is_overdue: 0,
    }));
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/dashboard/stats") return Response.json({ script_count: 0, article_count: 0, task_total: 8, task_pending: 8, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 });
      if (path === "/api/dashboard/recent-tasks") return Response.json(taskRows);
      if (path === "/api/dashboard/database-distribution") return Response.json([]);
      throw new Error(`Unexpected request: ${path}`);
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    const list = await screen.findByRole("list", { name: "未完成任务列表" });
    expect(list).toHaveClass("dashboard-task-list");
    expect(list).toHaveAttribute("tabindex", "0");
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
  });
});
