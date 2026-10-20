import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../pages/Dashboard";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("dashboard task queue", () => {
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
});
