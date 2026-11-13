import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DateField } from "../components/DateField";

afterEach(cleanup);

function show(initialValue = "") {
  render(<form><DateField name="due_date" label="截止日期" initialValue={initialValue} /></form>);
  return screen.getByRole("textbox", { name: "截止日期" }) as HTMLInputElement;
}

describe("task date field", () => {
  it("changes year and month, then submits the selected local date", async () => {
    const input = show("2026-11-19");
    expect(input).toHaveValue("2026-11-19");
    fireEvent.click(input);
    const calendar = within(await screen.findByRole("dialog", { name: "选择日期" }));
    fireEvent.change(calendar.getByRole("combobox", { name: "年份" }), { target: { value: "2028" } });
    fireEvent.change(calendar.getByRole("combobox", { name: "月份" }), { target: { value: "1" } });
    fireEvent.click(calendar.getByRole("gridcell", { name: /2028年2月29日/ }));
    expect(new FormData(input.form!).get("due_date")).toBe("2028-02-29");
  });

  it("accepts an empty deadline and rejects invalid typed dates", () => {
    const input = show();
    expect(input).toBeValid();
    expect(new FormData(input.form!).get("due_date")).toBe("");
    fireEvent.change(input, { target: { value: "2026-02-30" } });
    expect(input).toBeInvalid();
    fireEvent.blur(input);
    expect(input).toHaveValue("2026-02-30");
    fireEvent.change(input, { target: { value: "2028-02-29" } });
    expect(input).toBeValid();
    expect(new FormData(input.form!).get("due_date")).toBe("2028-02-29");
    fireEvent.click(screen.getByRole("button", { name: "清除日期" }));
    expect(input).toHaveValue("");
    expect(input).toBeValid();
  });
});
