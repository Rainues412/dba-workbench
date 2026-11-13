import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InputProtection } from "../components/InputProtection";
import { FileName } from "../components/FileName";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("lets IME select candidates, blocks shortcuts, and releases Enter after 500ms", () => {
  let now = 1000;
  vi.spyOn(performance, "now").mockImplementation(() => now);
  const shortcut = vi.fn();
  render(<InputProtection><input aria-label="输入" onKeyDown={shortcut} /></InputProtection>);
  const input = screen.getByLabelText("输入");
  fireEvent.compositionStart(input);
  expect(fireEvent.keyDown(input, { key: "Enter", isComposing: true })).toBe(true);
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "Escape" });
  expect(shortcut).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input);
  now += 499;
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(false);
  expect(shortcut).not.toHaveBeenCalled();
  now += 1;
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(true);
  expect(shortcut).toHaveBeenCalledTimes(1);
});

it("blocks composing form submissions without blocking a later explicit save", () => {
  const submit = vi.fn((event) => event.preventDefault());
  render(<InputProtection><form onSubmit={submit}><input aria-label="名称" /><button>保存</button></form></InputProtection>);
  const input = screen.getByLabelText("名称");
  input.focus();
  fireEvent.compositionStart(input);
  fireEvent.submit(input.closest("form")!);
  expect(submit).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input);
  fireEvent.click(screen.getByText("保存"));
  expect(submit).toHaveBeenCalledTimes(1);
});

it("handles native IME signals without a compositionstart and keeps cooldown per input", () => {
  const shortcut = vi.fn();
  render(<InputProtection><input aria-label="一" onKeyDown={shortcut} /><input aria-label="二" onKeyDown={shortcut} /></InputProtection>);
  fireEvent.keyDown(screen.getByLabelText("一"), { key: "Enter", keyCode: 229 });
  expect(shortcut).not.toHaveBeenCalled();
  fireEvent.compositionEnd(screen.getByLabelText("一"));
  fireEvent.keyDown(screen.getByLabelText("二"), { key: "Enter" });
  expect(shortcut).toHaveBeenCalledTimes(1);
});

it("preserves compound extensions only for actual filenames", () => {
  const { container, rerender } = render(<FileName text="备份.tar.gz" path="D:\\资料\\备份.tar.gz" />);
  expect(container.querySelector(".filename-extension")).toHaveTextContent(".tar.gz");
  expect(container).toHaveTextContent("备份.tar.gz");
  rerender(<FileName text="MySQL 8.0" path="D:\\资料\\note.md" />);
  expect(container.querySelector(".filename-extension")).toBeNull();
  rerender(<FileName text=".gitignore" path="D:\\资料\\.gitignore" />);
  expect(container.querySelector(".filename-extension")).toBeNull();
});
