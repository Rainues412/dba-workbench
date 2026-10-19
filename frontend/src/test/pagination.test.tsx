import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pagination } from "../components/Pagination";

afterEach(cleanup);

const example = { page: 18, pages: 354, total: 3536, pageSize: 10 };

describe("numbered pagination", () => {
  it("matches the reference layout with first, last and surrounding pages", () => {
    render(<Pagination {...example} onChange={vi.fn()} onPageSizeChange={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "每页条数" })).toHaveValue("10");
    expect(screen.getByText("共 3536 条")).toBeInTheDocument();
    const pager = screen.getByRole("navigation", { name: "列表分页" });
    expect(within(pager).getAllByRole("button", { name: /^第 \d+ 页$/ }).map((button) => button.textContent)).toEqual(["1", "16", "17", "18", "19", "20", "354"]);
    expect(screen.getByRole("button", { name: "第 18 页" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByText("···")).toHaveLength(2);
  });

  it("opens a numbered page or the final page directly", () => {
    const onChange = vi.fn();
    render(<Pagination {...example} onChange={onChange} onPageSizeChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "第 19 页" }));
    expect(onChange).toHaveBeenLastCalledWith(19);
    fireEvent.click(screen.getByRole("button", { name: "第 354 页" }));
    expect(onChange).toHaveBeenLastCalledWith(354);
  });

  it("uses the ellipses to jump by five pages", () => {
    const onChange = vi.fn();
    render(<Pagination {...example} onChange={onChange} onPageSizeChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "向前跳转至第 13 页" }));
    expect(onChange).toHaveBeenLastCalledWith(13);
    fireEvent.click(screen.getByRole("button", { name: "向后跳转至第 23 页" }));
    expect(onChange).toHaveBeenLastCalledWith(23);
  });

  it("changes the requested page size", () => {
    const onPageSizeChange = vi.fn();
    render(<Pagination {...example} onChange={vi.fn()} onPageSizeChange={onPageSizeChange} />);
    fireEvent.change(screen.getByRole("combobox", { name: "每页条数" }), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });

  it("shows every page for a short list and disables boundary arrows", () => {
    const props = { pages: 3, total: 25, pageSize: 10, onChange: vi.fn(), onPageSizeChange: vi.fn() };
    const { rerender } = render(<Pagination {...props} page={1} />);
    expect(screen.getAllByRole("button", { name: /^第 \d+ 页$/ })).toHaveLength(3);
    expect(screen.queryByText("···")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(props.onChange).toHaveBeenCalledWith(2);
    rerender(<Pagination {...props} page={3} />);
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });

  it.each([1, 2, 3, 352, 353, 354])("keeps the end pages without duplicate numbers near page %s", (page) => {
    render(<Pagination {...example} page={page} onChange={vi.fn()} onPageSizeChange={vi.fn()} />);
    const numbers = screen.getAllByRole("button", { name: /^第 \d+ 页$/ }).map((button) => button.textContent);
    expect(numbers[0]).toBe("1");
    expect(numbers.at(-1)).toBe("354");
    expect(new Set(numbers).size).toBe(numbers.length);
    expect(screen.getByRole("button", { name: `第 ${page} 页` })).toHaveAttribute("aria-current", "page");
  });

  it("handles an empty list without enabling invalid page changes", () => {
    render(<Pagination page={1} pages={0} total={0} pageSize={10} onChange={vi.fn()} onPageSizeChange={vi.fn()} />);
    expect(screen.getByText("共 0 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });
});
