import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DesktopDragRegion } from "../components/DesktopWindowControls";

afterEach(cleanup);

it("hands a drag to Windows once and keeps double-click separate", () => {
  const startDrag = vi.fn();
  const toggleSize = vi.fn();
  render(<DesktopDragRegion actions={{ maximized: false, minimize: vi.fn(), toggleSize, startDrag, close: vi.fn() }}>
    <span>工作台</span>
  </DesktopDragRegion>);
  const region = screen.getByText("工作台").parentElement!;
  region.setPointerCapture = vi.fn();
  region.releasePointerCapture = vi.fn();

  fireEvent.pointerDown(region, { pointerType: "mouse", pointerId: 1, button: 0, clientX: 20, clientY: 20 });
  fireEvent.pointerMove(region, { pointerType: "mouse", pointerId: 1, buttons: 1, clientX: 22, clientY: 21 });
  expect(startDrag).not.toHaveBeenCalled();
  fireEvent.pointerMove(region, { pointerType: "mouse", pointerId: 1, buttons: 1, clientX: 32, clientY: 20 });
  fireEvent.pointerMove(region, { pointerType: "mouse", pointerId: 1, buttons: 1, clientX: 42, clientY: 20 });
  expect(startDrag).toHaveBeenCalledTimes(1);
  expect(region.releasePointerCapture).toHaveBeenCalledWith(1);

  fireEvent.doubleClick(region);
  expect(toggleSize).toHaveBeenCalledOnce();
});
