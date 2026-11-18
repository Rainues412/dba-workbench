import { useEffect, useRef, useState, type ReactNode } from "react";
import { Copy, Minus, Square, X } from "lucide-react";

type DesktopWindowApi = {
  minimize: () => Promise<void>;
  window_is_maximized: () => Promise<boolean>;
  toggle_window_size: () => Promise<boolean>;
  start_window_drag: () => Promise<void>;
  destroy: () => Promise<void>;
};

function getApi() {
  const api = (window as Window & { pywebview?: { api: Partial<DesktopWindowApi> } }).pywebview?.api;
  return api?.minimize && api.window_is_maximized && api.toggle_window_size && api.start_window_drag && api.destroy ? api as DesktopWindowApi : null;
}

export function useDesktopWindow() {
  const [api, setApi] = useState(getApi);
  const [maximized, setMaximized] = useState(true);

  useEffect(() => {
    const ready = () => {
      const current = getApi();
      setApi(current);
      if (current) void current.window_is_maximized().then(setMaximized);
    };
    window.addEventListener("pywebviewready", ready);
    ready();
    return () => window.removeEventListener("pywebviewready", ready);
  }, []);

  useEffect(() => {
    if (!api) return;
    let timer: number;
    const scheduleSync = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void api.window_is_maximized().then(setMaximized), 120);
    };
    window.addEventListener("resize", scheduleSync);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", scheduleSync);
    };
  }, [api]);

  if (!api) return null;
  return {
    maximized,
    minimize: () => void api.minimize(),
    toggleSize: () => void api.toggle_window_size().then(setMaximized),
    startDrag: () => void api.start_window_drag(),
    close: () => void api.destroy(),
  };
}

export function DesktopDragRegion({ actions, children }: { actions: ReturnType<typeof useDesktopWindow>; children: ReactNode }) {
  const pointerOrigin = useRef<{ x: number; y: number } | null>(null);
  if (!actions) return <div className="topbar-title">{children}</div>;
  return <div className="topbar-title"
    onPointerDown={(event) => {
      if (event.button !== 0 || event.pointerType !== "mouse") return;
      pointerOrigin.current = { x: event.clientX, y: event.clientY };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={(event) => {
      const origin = pointerOrigin.current;
      if (!origin || !(event.buttons & 1) || Math.hypot(event.clientX - origin.x, event.clientY - origin.y) < 4) return;
      pointerOrigin.current = null;
      event.currentTarget.releasePointerCapture(event.pointerId);
      actions.startDrag();
    }}
    onLostPointerCapture={() => { pointerOrigin.current = null; }}
    onDoubleClick={actions.toggleSize}
  >{children}</div>;
}

export function DesktopWindowControls({ actions }: { actions: NonNullable<ReturnType<typeof useDesktopWindow>> }) {
  const sizeLabel = actions.maximized ? "还原窗口" : "最大化窗口";
  return <div className="desktop-window-controls" role="group" aria-label="窗口控制">
    <button type="button" aria-label="最小化窗口" title="最小化窗口" onClick={actions.minimize}><Minus size={15} aria-hidden="true" /></button>
    <button type="button" aria-label={sizeLabel} title={sizeLabel} onClick={actions.toggleSize}>{actions.maximized ? <Copy size={13} aria-hidden="true" /> : <Square size={13} aria-hidden="true" />}</button>
    <button type="button" className="desktop-window-close" aria-label="关闭到托盘" title="关闭到托盘" onClick={actions.close}><X size={16} aria-hidden="true" /></button>
  </div>;
}
