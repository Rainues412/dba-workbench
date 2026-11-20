import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { LibraryRecords } from "../components/LibraryRecords";
import { articlesConfig, resourcesConfig, scriptsConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each([articlesConfig, scriptsConfig])("$key opens from card content and keeps nested actions independent", async (config) => {
  const onPreview = vi.fn();
  const onEdit = vi.fn();
  const onUpdate = vi.fn(async () => {});
  const onRemove = vi.fn(async () => {});
  const row = { id: 1, revision: 1, title: "短", wb_db: "Oracle", db_type: "Oracle", category: "日常管理", file_path: "D:/docs/short.md" };
  render(<MemoryRouter><LibraryRecords config={config} rows={[row]} selectedId={1} disabled={false} onPreview={onPreview} onEdit={onEdit} onUpdate={onUpdate} onRemove={onRemove} onNotice={() => {}} /></MemoryRouter>);
  const title = screen.getByRole("button", { name: "预览：短" });
  const card = title.closest("li")!;
  for (const target of [card, card.querySelector(".library-record-icon")!, card.querySelector(".library-record-path")!, card.querySelector(".library-record-meta")!, title]) {
    fireEvent.click(target);
  }
  expect(onPreview.mock.calls).toEqual(Array.from({ length: 5 }, () => [1]));
  expect(title).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "查看/编辑" }).querySelector("svg")!);
  expect(onEdit).toHaveBeenCalledExactlyOnceWith(1);
  fireEvent.click(screen.getByRole("button", { name: "收藏" }));
  expect(onUpdate).toHaveBeenCalledExactlyOnceWith(row, { is_favorite: 1 });
  fireEvent.click(screen.getByLabelText("更多操作：短"));
  fireEvent.click(screen.getByRole("button", { name: "删除记录" }));
  expect(onRemove).toHaveBeenCalledExactlyOnceWith(row);
  expect(onPreview).toHaveBeenCalledTimes(5);
  // Selecting a path to copy it should not toggle the preview on mouse release.
  vi.spyOn(window, "getSelection").mockReturnValue({ isCollapsed: false, anchorNode: card.querySelector(".library-record-path")!.firstChild } as Selection);
  fireEvent.click(card.querySelector(".library-record-path")!);
  expect(onPreview).toHaveBeenCalledTimes(5);
});

it.each([articlesConfig, resourcesConfig])("$key does not add card actions to disabled rows or resources", (config) => {
  const onPreview = vi.fn();
  render(<MemoryRouter><LibraryRecords config={config} rows={[{ id: 1, revision: 1, title: "短", name: "短" }]} selectedId={null} disabled={config.key === "articles"} onPreview={onPreview} onEdit={() => {}} onUpdate={async () => {}} onRemove={async () => {}} onNotice={() => {}} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("listitem"));
  expect(onPreview).not.toHaveBeenCalled();
});
