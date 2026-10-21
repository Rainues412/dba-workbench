import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../pages/Dashboard";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("dashboard task queue", () => {
  it("renders MongoDB as its own database distribution item", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/dashboard/stats") return Response.json({ script_count: 1, article_count: 1, task_total: 0, task_pending: 0, task_overdue: 0, customer_count: 0, resource_count: 0, password_count: 0 });
      if (path === "/api/dashboard/recent-tasks") return Response.json([]);
      if (path === "/api/dashboard/database-distribution") return Response.json([{ name: "MongoDB", count: 2 }]);
      throw new Error(`Unexpected request: ${path}`);
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<MemoryRouter><QueryClientProvider client={client}><Dashboard /></QueryClientProvider></MemoryRouter>);

    expect(await screen.findByText("MongoDB")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "完成任务：处理逾期任务" }));

    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].path).toBe("/api/tasks/7");
    expect(new Headers(writes[0].init?.headers).get("If-Match")).toBe("3");
    expect(JSON.parse(String(writes[0].init?.body))).toEqual({ status: "已完成" });
    expect(await screen.findByText("任务队列已清空")).toBeInTheDocument();
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
