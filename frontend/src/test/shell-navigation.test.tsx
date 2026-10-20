import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Shell } from "../components/Shell";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ session: { user: { username: "owner" } }, logout: vi.fn() }),
}));
vi.mock("../components/DataBackup", () => ({ DataBackup: () => null }));

describe("sidebar navigation", () => {
  it("places the knowledge base after the dashboard and labels collapsed controls", () => {
    render(<MemoryRouter><Routes><Route element={<Shell />}><Route index element={<div>首页</div>} /></Route></Routes></MemoryRouter>);

    const navigation = screen.getByRole("navigation", { name: "主导航" });
    expect(within(navigation).getAllByRole("link").slice(0, 3).map((link) => link.getAttribute("aria-label")))
      .toEqual(["工作台", "知识库", "脚本库"]);

    const toggle = screen.getByRole("button", { name: "收起侧栏" });
    expect(toggle).toHaveAttribute("title", "收起侧栏");
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "展开侧栏" })).toHaveAttribute("title", "展开侧栏");
    expect(within(navigation).getByRole("link", { name: "知识库" })).toHaveAttribute("title", "知识库：文档沉淀");
    expect(screen.getByRole("link", { name: "返回工作台" })).toHaveAttribute("title", "返回工作台");
  });
});
