import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage } from "../components/CrudPage";
import { customersConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={customersConfig} /></QueryClientProvider></MemoryRouter>);
}

const blankChat = { name: "", platform: "" };
const profile = {
  chat: { name: "示例客户群", platform: "企业微信" },
  owners: [{ name: "王经理", label: "客户统筹" }],
  projects: [7, 2, 6, 4, 1, 3, 5].map((number) => ({
    name: `项目 ${number}`,
    chat: number === 1 ? { name: "迁移协作群", platform: "钉钉" } : blankChat,
    owners: number === 1 ? [{ name: "张三", label: "资源开通" }, { name: "李四", label: "技术支持" }] : [],
  })),
};
const customer = { id: 5, revision: 7, name: "示例客户", status: "活跃", notes: "完整备注", project_profile: profile };
const list = (items: unknown[]) => Response.json({ items, page: 1, total: items.length, pages: items.length ? 1 : 0 });

describe("customer project directory", () => {
  it("keeps the only project collapsed while showing the customer's initial and shared chat", async () => {
    const single = { ...customer, project_profile: { ...profile, projects: [profile.projects[4]] } };
    vi.stubGlobal("fetch", vi.fn(async () => list([single])));
    show();
    const toggle = await screen.findByRole("button", { name: /示例客户.*1 个项目/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("迁移协作群")).not.toBeInTheDocument();
    expect(screen.getByText("示例客户群")).toBeVisible();
    expect(screen.getByText("示", { selector: ".customer-avatar" })).toBeVisible();
    fireEvent.click(toggle);
    expect(screen.getByText("迁移协作群")).toBeVisible();
    expect(screen.getByText("资源开通")).toBeVisible();
  });

  it("opens one customer's sorted projects and only shows the first five until expanded", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => list([customer])));
    show();
    const toggle = await screen.findByRole("button", { name: /示例客户.*7 个项目/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText("示例客户群")).toBeVisible();
    expect(screen.getByText("王经理")).toBeVisible();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent)).toEqual(["项目 1", "项目 2", "项目 3", "项目 4", "项目 5"]);
    const project = within(table).getAllByRole("row")[1];
    for (const value of ["迁移协作群", "钉钉", "张三", "资源开通", "李四", "技术支持"]) expect(within(project).getByText(value)).toBeVisible();
    expect(within(table).getAllByText("沿用客户负责人")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: /查看更多/ }));
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(screen.getByRole("table")).toBeVisible();
    expect(screen.queryByText("项目 6")).not.toBeInTheDocument();
  });

  it("saves custom names and roles on the intended project with the record revision", async () => {
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT") { writes.push(init); return Response.json({ ...customer, revision: 8 }); }
      if (path === "/api/customers/5") return Response.json({ ...customer, project_profile: { ...profile, projects: [profile.projects[4]] }, contacts: [], communications: [{ content: "旧记录" }] });
      return list([customer]);
    }));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "查看/编辑" }));
    expect(await screen.findByLabelText("客户群聊名")).toHaveValue("示例客户群");
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("备注")).toHaveValue(customer.notes);
    expect(within(dialog).queryByText("旧记录")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "新增项目" }));
    const project = within(within(dialog).getByRole("group", { name: "项目 1" }));
    const projectName = project.getByLabelText("项目名");
    expect(projectName).toHaveFocus();
    expect(projectName).toHaveValue("");
    fireEvent.change(projectName, { target: { value: "项目 10" } });
    expect(projectName).toHaveFocus();
    fireEvent.change(project.getByLabelText("项目群聊平台"), { target: { value: "微信" } });
    fireEvent.click(project.getByRole("button", { name: "添加项目负责人" }));
    fireEvent.change(project.getByLabelText("负责人姓名"), { target: { value: "赵五" } });
    fireEvent.change(project.getByLabelText("职责标签"), { target: { value: "巡检交付" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(new Headers(writes[0].headers).get("If-Match")).toBe("7");
    expect(JSON.parse(String(writes[0].body))).toEqual({
      name: customer.name, status: customer.status, notes: customer.notes,
      project_profile: {
        chat: profile.chat, owners: profile.owners,
        projects: [profile.projects[4], { name: "项目 10", chat: { name: "", platform: "微信" }, owners: [{ name: "赵五", label: "巡检交付" }] }],
      },
    });
  });
});
