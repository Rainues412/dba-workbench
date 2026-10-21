import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage } from "../components/CrudPage";
import { customersConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={customersConfig} /></QueryClientProvider></MemoryRouter>);
}

const customer = { id: 5, revision: 7, name: "长客户名称".repeat(15), project_name: "数据库平台升级", group_name: "华东客户", status: "进行中", wb_person: "张三", wb_contact: "13800000000 / zhang@example.test", notes: "完整客户备注\n第二行", contacts: [], communications: [], tasks: [] };

describe("customer project layout", () => {
  it("shows existing group and contact information, groups fields, and preserves all detail fields when saving", async () => {
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT") { writes.push(init); return Response.json({ ...customer, revision: 8 }); }
      if (path === "/api/customers/5") return Response.json(customer);
      return Response.json({ items: [{ ...customer, notes: undefined }], page: 1, total: 1, page_size: 10, pages: 1 });
    }));
    show();
    expect(await screen.findByText(customer.name)).toHaveAttribute("title", customer.name);
    expect(screen.getByText(customer.group_name)).toBeInTheDocument();
    expect(screen.getByText(customer.wb_contact)).toHaveAttribute("title", customer.wb_contact);
    expect(screen.getByText(customer.project_name)).toHaveAttribute("title", customer.project_name);
    fireEvent.click(screen.getByRole("button", { name: "查看/编辑" }));
    const group = await screen.findByRole("group", { name: "基本信息" });
    expect(within(group).getByLabelText("客户")).toHaveValue(customer.name);
    expect(within(group).getByLabelText("项目")).toHaveValue(customer.project_name);
    const owner = screen.getByRole("group", { name: "负责人信息" });
    fireEvent.change(within(owner).getByLabelText("负责人"), { target: { value: "李四" } });
    expect(within(screen.getByRole("group", { name: "备注" })).getByLabelText("备注")).toHaveValue(customer.notes);
    expect(screen.getByRole("region", { name: /关联联系人/ })).toHaveTextContent("暂无联系人");
    expect(screen.getByRole("region", { name: /沟通记录/ })).toHaveTextContent("暂无沟通记录");
    expect(screen.getByRole("region", { name: /关联任务/ })).toHaveTextContent("暂无关联任务");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(new Headers(writes[0].headers).get("If-Match")).toBe("7");
    expect(JSON.parse(String(writes[0].body))).toEqual({ name: customer.name, project_name: customer.project_name, group_name: customer.group_name, status: customer.status, wb_person: "李四", wb_contact: customer.wb_contact, notes: customer.notes });
  });

  it("creates a customer from the grouped form without showing persisted relations", async () => {
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_path: string, init?: RequestInit) => {
      if (init?.method === "POST") { writes.push(init); return Response.json(customer); }
      return Response.json({ items: [], total: 0, page: 1, page_size: 10, pages: 0 });
    }));
    show();
    await screen.findByText("没有客户项目数据");
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    fireEvent.change(screen.getByLabelText("客户"), { target: { value: "新客户" } });
    expect(screen.getByLabelText("状态")).toHaveValue("活跃");
    expect(screen.queryByRole("region", { name: "客户关联信息" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(JSON.parse(String(writes[0].body))).toMatchObject({ name: "新客户", notes: "", status: "活跃" });
  });
});
