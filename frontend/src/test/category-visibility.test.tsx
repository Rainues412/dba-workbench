import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CategoryNavigation, type Facets } from "../components/CategoryNavigation";

afterEach(cleanup);
const data: Facets = { total: 6, items: [
  { wb_db: "Oracle", category: "性能优化", count: 2 },
  { wb_db: "Oracle", category: "新导入的自定义主题", count: 1 },
  { wb_db: "MySQL", category: "备份与恢复", count: 3 },
  { wb_db: "MySQL", category: "空主题", count: 0 },
] };
const props = {
  classification: { databaseField: "wb_db", categoryField: "category", categoryLabel: "文档分类" },
  data, database: "", category: "", categoryOptions: ["备份与恢复", "性能优化", "空主题", "尚未使用的主题"],
  hideEmptyCategories: true, loading: false, error: false, retry: vi.fn(), onChange: vi.fn(),
};
const buttons = () => within(screen.getByRole("group", { name: "文档分类" })).getAllByRole("button").map((button) => button.textContent);

describe("knowledge category visibility", () => {
  it("uses all-database counts and includes populated categories absent from the preset list", () => {
    render(<CategoryNavigation {...props} />);
    expect(buttons()).toEqual(["全部6", "备份与恢复3", "性能优化2", "新导入的自定义主题1"]);
  });

  it("recomputes visibility for each selected database rather than using global category counts", () => {
    const { rerender } = render(<CategoryNavigation {...props} database="Oracle" />);
    expect(buttons()).toEqual(["全部3", "性能优化2", "新导入的自定义主题1"]);
    rerender(<CategoryNavigation {...props} database="MySQL" />);
    expect(buttons()).toEqual(["全部3", "备份与恢复3"]);
  });

  it("automatically shows a topic on its first article and hides it after its last article is removed", () => {
    const { rerender } = render(<CategoryNavigation {...props} database="MySQL" />);
    const withFirstArticle = { total: 7, items: [...data.items, { wb_db: "MySQL", category: "性能优化", count: 1 }] };
    rerender(<CategoryNavigation {...props} database="MySQL" data={withFirstArticle} />);
    expect(buttons()).toEqual(["全部4", "备份与恢复3", "性能优化1"]);
    rerender(<CategoryNavigation {...props} database="MySQL" />);
    expect(buttons()).toEqual(["全部3", "备份与恢复3"]);
  });

  it("does not force an empty selected URL category into the menu and keeps the reset entry", () => {
    const onChange = vi.fn();
    render(<CategoryNavigation {...props} database="Redis" category="性能优化" onChange={onChange} />);
    expect(buttons()).toEqual(["全部0"]);
    fireEvent.click(screen.getByRole("button", { name: /^全部/ }));
    expect(onChange).toHaveBeenCalledWith("Redis", "");
  });

  it("does not present preset topics as populated during loading or a failed initial fetch", () => {
    const retry = vi.fn();
    const { rerender } = render(<CategoryNavigation {...props} data={undefined} loading />);
    expect(buttons()).toEqual(["全部0"]);
    expect(screen.getByText("正在读取分类")).toBeInTheDocument();
    rerender(<CategoryNavigation {...props} data={undefined} error retry={retry} />);
    expect(buttons()).toEqual(["全部0"]);
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("preserves zero-count navigation options for modules that have not enabled this behavior", () => {
    render(<CategoryNavigation {...props} hideEmptyCategories={false} database="MySQL" />);
    expect(buttons()).toContain("性能优化0");
    expect(buttons()).toContain("尚未使用的主题0");
  });
});
