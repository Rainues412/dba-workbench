import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pagination } from "../components/Pagination";

afterEach(cleanup);

describe("direct page navigation", () => {
  it("jumps directly to a valid requested page", () => {
    const onChange = vi.fn();
    render(<Pagination page={1} pages={40} onChange={onChange} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: "跳转页码" }), { target: { value: "31" } });
    fireEvent.click(screen.getByRole("button", { name: "跳转" }));
    expect(onChange).toHaveBeenCalledWith(31);
    expect(screen.getByRole("spinbutton")).toHaveValue(null);
  });

  it.each(["", "0", "41", "2.5"])("rejects an invalid or out-of-range page: %s", (value) => {
    const onChange = vi.fn();
    render(<Pagination page={1} pages={40} onChange={onChange} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "跳转" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请输入 1 至 40 的整数页码");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("disables previous and next at the page boundaries", () => {
    const onChange = vi.fn();
    const { rerender } = render(<Pagination page={1} pages={3} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(onChange).toHaveBeenCalledWith(2);
    rerender(<Pagination page={3} pages={3} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });
});
