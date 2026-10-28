import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { VaultCategoryInput } from "../components/VaultCategoryInput";

afterEach(cleanup);

describe("vault category combobox", () => {
  it("filters typed text, supports keyboard selection, and reopens all categories", () => {
    render(<VaultCategoryInput categories={["Coding", "Database", "工作"]} initialValue="工作" />);
    const input = screen.getByRole("combobox", { name: "分类" });
    expect(input).toHaveValue("工作");
    fireEvent.click(screen.getByRole("button", { name: "选择已有分类" }));
    expect(screen.getAllByRole("option")).toHaveLength(3);
    fireEvent.click(screen.getByRole("option", { name: "Database" }));
    expect(input).toHaveValue("Database");
    expect(input).toHaveAttribute("aria-expanded", "false");
    fireEvent.change(input, { target: { value: "cod" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input).toHaveValue("Coding");
    fireEvent.click(screen.getByRole("button", { name: "选择已有分类" }));
    expect(screen.getAllByRole("option")).toHaveLength(3);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveValue("Coding");
    fireEvent.change(input, { target: { value: "新类别" } });
    fireEvent.blur(input);
    expect(input).toHaveValue("新类别");
  });
});
