import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage } from "../components/CrudPage";
import { articlesConfig, scriptsConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("classification editor", () => {
  for (const config of [articlesConfig, scriptsConfig]) {
    const fieldName = config.classification!.categoryField!;
    const field = config.fields.find((candidate) => candidate.name === fieldName)!;
    const databaseField = config.classification!.databaseField;

    it.each([false, true])(`${config.key} shows every category while editing, including when facets fail: %s`, async (facetsFail) => {
      const row = { id: 7, revision: 4, title: "编辑分类测试", [databaseField]: "Oracle", [fieldName]: "旧自定义分类", content: "正文保持完整" };
      const writes: RequestInit[] = [];
      vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
        if (init?.method === "PUT") { writes.push(init); return Response.json({ ...row, ...JSON.parse(String(init.body)), revision: 5 }); }
        if (path === `${config.path}facets`) return facetsFail ? Response.json({}, { status: 500 }) : Response.json({ total: 30, items: [
          { [databaseField]: "Oracle", [fieldName]: field.options![0], count: 10 },
          { [databaseField]: "MySQL", [fieldName]: "其他页自定义分类", count: 20 },
        ] });
        if (path === `${config.path}7`) return Response.json(row);
        return Response.json({ total: 30, items: [row], page: 1, page_size: 10, pages: 3 });
      }));
      const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
      render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={config} /></QueryClientProvider></MemoryRouter>);
      // Active list filters must not narrow the choices available to the editor.
      if (!facetsFail) {
        fireEvent.click(await screen.findByRole("combobox", { name: "筛选数据库" }));
        fireEvent.click(await screen.findByRole("option", { name: "Oracle（10）" }));
      }
      await waitFor(() => expect(screen.getByRole("button", { name: "查看/编辑" })).not.toBeDisabled());
      fireEvent.click(await screen.findByRole("button", { name: "查看/编辑" }));
      const select = await screen.findByRole("combobox", { name: field.label });
      const dialog = screen.getByRole("dialog");
      expect(select.tagName).toBe("SELECT");
      expect(within(dialog).getByLabelText(field.label, { exact: true })).toBe(select);
      expect(select).toHaveValue("旧自定义分类");
      const expected = [...field.options!, ...(!facetsFail ? ["其他页自定义分类"] : []), "旧自定义分类"];
      expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(expected);
      fireEvent.change(select, { target: { value: field.options![1] } });
      expect(select).toHaveAttribute("title", field.options![1]);
      fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
      await waitFor(() => expect(writes).toHaveLength(1));
      expect(new Headers(writes[0].headers).get("If-Match")).toBe("4");
      expect(JSON.parse(String(writes[0].body))).toMatchObject({ [fieldName]: field.options![1], content: "正文保持完整" });
    });

    it.each(["", "自定义保留值"])(`${config.key} preserves unchanged category %j on save`, async (category) => {
      const row = { id: 1, revision: 2, title: "保留分类测试", [fieldName]: category };
      const writes: RequestInit[] = [];
      vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
        if (init?.method === "PUT") { writes.push(init); return Response.json(row); }
        if (path.endsWith("facets")) return Response.json({ total: 0, items: [] });
        if (path === `${config.path}1`) return Response.json(row);
        return Response.json({ total: 1, items: [row], page: 1, page_size: 10, pages: 1 });
      }));
      const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
      render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={config} /></QueryClientProvider></MemoryRouter>);
      fireEvent.click(await screen.findByRole("button", { name: "查看/编辑" }));
      const select = await screen.findByRole("combobox", { name: field.label });
      expect(select).toHaveValue(category);
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "保存" }));
      await waitFor(() => expect(writes).toHaveLength(1));
      expect(JSON.parse(String(writes[0].body))[fieldName]).toBe(category);
    });
  }
});
