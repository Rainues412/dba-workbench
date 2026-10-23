import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CategoryNavigation } from "../components/CategoryNavigation";
import { databaseMeta } from "../components/DatabaseLabel";

afterEach(cleanup);
const custom = "达梦-" + "很长的数据库名称".repeat(8);
const facets = { total: 8, items: [
  { wb_db: "Oracle", kind: "安装包", count: 5 },
  { wb_db: custom, kind: "自定义类型", count: 3 },
] };

function Example({ change = () => undefined }: { change?: (database: string, category: string) => void }) {
  const [database, setDatabase] = useState("Oracle");
  return <><CategoryNavigation classification={{ databaseField: "wb_db", categoryField: "kind", categoryLabel: "类型" }}
    database={database} category="" onChange={(db, category) => { setDatabase(db); change(db, category); }}
    data={facets} loading={false} error={false} retry={() => undefined} /><button>外部按钮</button></>;
}

describe("database icon select", () => {
  it("shows the selected icon once and reuses each database asset in the dropdown", () => {
    const change = vi.fn();
    render(<Example change={change} />);
    const combo = screen.getByRole("combobox", { name: "筛选数据库" });
    const group = screen.getByRole("group", { name: "数据库分类" });
    expect(within(group).getAllByText("Oracle")).toHaveLength(1);
    expect(combo.querySelector("img")).toHaveAttribute("src", databaseMeta.Oracle.icon);
    expect(combo).toHaveAttribute("title", "Oracle（5）");
    fireEvent.click(combo);
    const list = screen.getByRole("listbox", { name: "数据库" });
    for (const name of Object.keys(databaseMeta)) {
      const option = within(list).getByRole("option", { name: `${name}（${name === "Oracle" ? 5 : 0}）` });
      expect(option.querySelector(".database-logo")).not.toBeNull();
      if (databaseMeta[name].icon) expect(option.querySelector("img")).toHaveAttribute("src", databaseMeta[name].icon);
    }
    const option = within(list).getByRole("option", { name: `${custom}（3）` });
    expect(option).toHaveAttribute("title", `${custom}（3）`);
    expect(option.querySelector("img")).toHaveAttribute("src", databaseMeta["其他"].icon);
    fireEvent.click(option);
    expect(change).toHaveBeenCalledWith(custom, "");
    expect(combo).toHaveAttribute("title", `${custom}（3）`);
    expect(combo).toHaveAttribute("aria-expanded", "false");
    expect(combo).toHaveFocus();
  });

  it("supports arrow navigation, Escape cancellation, typeahead and Home/End confirmation", () => {
    const change = vi.fn();
    render(<Example change={change} />);
    const combo = screen.getByRole("combobox", { name: "筛选数据库" });
    combo.focus();
    fireEvent.keyDown(combo, { key: "ArrowDown" });
    fireEvent.keyDown(combo, { key: "ArrowDown" });
    expect(document.getElementById(combo.getAttribute("aria-activedescendant")!)).toHaveTextContent("MySQL");
    expect(change).not.toHaveBeenCalled();
    fireEvent.keyDown(combo, { key: "Escape" });
    expect(combo).toHaveTextContent("Oracle");
    expect(combo).not.toHaveAttribute("aria-activedescendant");
    fireEvent.keyDown(combo, { key: "m" });
    fireEvent.keyDown(combo, { key: "Enter" });
    expect(change).toHaveBeenLastCalledWith("MySQL", "");
    fireEvent.keyDown(combo, { key: "End" });
    fireEvent.keyDown(combo, { key: " " });
    expect(change).toHaveBeenLastCalledWith(custom, "");
    fireEvent.keyDown(combo, { key: "Home" });
    fireEvent.keyDown(combo, { key: "Tab" });
    expect(change).toHaveBeenLastCalledWith("", "");
    expect(combo).toHaveTextContent("全部数据库");
  });

  it("closes on outside click or focus without changing the selection", () => {
    const change = vi.fn();
    render(<Example change={change} />);
    const combo = screen.getByRole("combobox", { name: "筛选数据库" });
    fireEvent.click(combo);
    fireEvent.pointerDown(screen.getByRole("button", { name: "外部按钮" }));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.click(combo);
    fireEvent.focusIn(screen.getByRole("button", { name: "外部按钮" }));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(change).not.toHaveBeenCalled();
  });
});
