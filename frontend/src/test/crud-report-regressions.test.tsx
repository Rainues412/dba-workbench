import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage, type CrudConfig } from "../components/CrudPage";
import { articlesConfig, tasksConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function show(config: CrudConfig) {
  vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={config} /></QueryClientProvider></MemoryRouter>);
}
function listResponse(path: string, row: Record<string, unknown>, total = 1) {
  const page = Number(new URL(path, "http://localhost").searchParams.get("page"));
  return Response.json({ items: [row], total, page, page_size: 10, pages: Math.ceil(total / 10), has_next: page < Math.ceil(total / 10), has_previous: page > 1 });
}

describe("review report CRUD regressions", () => {
  it.each([500, 404])("does not show a create/save form after detail HTTP %s; retry updates the existing revision", async (status) => {
    let failing = true;
    const row = { id: 7, revision: 6, title: "已有任务", priority: "高", status: "待处理", due_date: "", description: "" };
    const writes: Array<{ path: string; init: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT" || init?.method === "POST") { writes.push({ path, init }); return Response.json(row); }
      if (path.startsWith("/api/tasks/?")) return listResponse(path, row);
      if (path === "/api/tasks/7") return failing ? Response.json({}, { status }) : Response.json(row);
      throw new Error(`Unexpected request: ${path}`);
    }));
    show(tasksConfig);
    fireEvent.click(await screen.findByRole("button", { name: "查看/编辑" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("详情加载失败，未进入新增模式，请重试");
    expect(within(dialog).getByRole("heading", { name: "编辑任务" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("heading", { name: "新增任务" })).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("任务")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    expect(dialog.querySelector("form")).toBeNull();
    expect(writes).toHaveLength(0);
    failing = false;
    fireEvent.click(within(dialog).getByRole("button", { name: "重试" }));
    const title = await screen.findByLabelText("任务");
    expect(title).toHaveValue("已有任务");
    fireEvent.change(title, { target: { value: "修改后的任务" } });
    fireEvent.submit(title.closest("form")!);
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].path).toBe("/api/tasks/7");
    expect(writes[0].init.method).toBe("PUT");
    expect(new Headers(writes[0].init.headers).get("If-Match")).toBe("6");
    expect(JSON.parse(String(writes[0].init.body)).title).toBe("修改后的任务");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("sends combined task status/priority filters and resets pagination to page one", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      requests.push(path);
      return listResponse(path, { id: 2, revision: 1, title: "筛选任务", priority: "高", status: "进行中" }, 30);
    }));
    show(tasksConfig);
    await screen.findByText("筛选任务");
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "第 2 页" })).toHaveAttribute("aria-current", "page"));
    fireEvent.change(screen.getByLabelText("筛选任务状态"), { target: { value: "进行中" } });
    await waitFor(() => {
      const params = new URL(requests.at(-1)!, "http://localhost").searchParams;
      expect(params.get("status")).toBe("进行中");
      expect(params.get("page")).toBe("1");
    });
    fireEvent.change(screen.getByLabelText("筛选任务优先级"), { target: { value: "高" } });
    await waitFor(() => {
      const params = new URL(requests.at(-1)!, "http://localhost").searchParams;
      expect(params.get("status")).toBe("进行中");
      expect(params.get("priority")).toBe("高");
      expect(params.get("page")).toBe("1");
    });
    fireEvent.change(screen.getByLabelText("筛选任务状态"), { target: { value: "" } });
    await waitFor(() => {
      const params = new URL(requests.at(-1)!, "http://localhost").searchParams;
      expect(params.has("status")).toBe(false);
      expect(params.get("priority")).toBe("高");
    });
  });

  it("toggles article favorite and pin using the latest row revision and supports favorite filtering", async () => {
    let row = { id: 5, revision: 3, title: "知识条目", is_favorite: 0, is_pinned: 0 };
    const writes: Array<{ path: string; init: RequestInit }> = [];
    const reads: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        writes.push({ path, init });
        row = { ...row, ...JSON.parse(String(init.body)), revision: row.revision + 1 };
        return Response.json(row);
      }
      reads.push(path);
      return listResponse(path, row);
    }));
    show({ ...articlesConfig, classification: undefined, fileLinks: undefined, columns: [{ name: "title", label: "标题" }] });
    fireEvent.click(await screen.findByRole("button", { name: /^收藏$/ }));
    await screen.findByRole("button", { name: "取消收藏" });
    expect(writes[0].path).toBe("/api/articles/5");
    expect(new Headers(writes[0].init.headers).get("If-Match")).toBe("3");
    expect(JSON.parse(String(writes[0].init.body))).toEqual({ is_favorite: 1 });
    fireEvent.click(screen.getByRole("button", { name: /^置顶$/ }));
    await screen.findByRole("button", { name: "取消置顶" });
    expect(new Headers(writes[1].init.headers).get("If-Match")).toBe("4");
    expect(JSON.parse(String(writes[1].init.body))).toEqual({ is_pinned: 1 });
    fireEvent.click(screen.getByRole("button", { name: "取消收藏" }));
    await screen.findByRole("button", { name: /^收藏$/ });
    expect(new Headers(writes[2].init.headers).get("If-Match")).toBe("5");
    expect(JSON.parse(String(writes[2].init.body))).toEqual({ is_favorite: 0 });
    fireEvent.click(screen.getByRole("button", { name: "取消置顶" }));
    await screen.findByRole("button", { name: /^置顶$/ });
    expect(new Headers(writes[3].init.headers).get("If-Match")).toBe("6");
    expect(JSON.parse(String(writes[3].init.body))).toEqual({ is_pinned: 0 });
    fireEvent.click(screen.getByRole("checkbox", { name: "只看收藏" }));
    await waitFor(() => expect(new URL(reads.at(-1)!, "http://localhost").searchParams.get("favorite_only")).toBe("1"));
  });
});
