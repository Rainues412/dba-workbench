import { useEffect, useRef, useState, type ReactNode, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { Group, Panel, Separator, useGroupRef } from "react-resizable-panels";
import { GripVertical } from "lucide-react";

type Preferences = { collapsed: boolean };

function readPreferences(key: string): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "{}");
    return { collapsed: value?.collapsed === true };
  } catch { return { collapsed: false }; }
}

// Categories stay outside the resizable group: dragging can only change the list/preview split.
export function LibraryLayout({ module, enabled, categories, preview, previewOpen = true, onPreviewClose, children }: {
  module: string;
  enabled: boolean;
  categories?: (collapsed: boolean, toggle: () => void) => ReactNode;
  preview?: ReactNode;
  previewOpen?: boolean;
  onPreviewClose?: () => void;
  children: ReactNode;
}) {
  const storageKey = `dba-library-layout:${module}`;
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey));
  const [wide, setWide] = useState(() => typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 1400px)").matches);
  const groupRef = useGroupRef();
  const groupElement = useRef<HTMLDivElement>(null);
  const cancelDrag = useRef<(() => void) | null>(null);
  const [dragging, setDragging] = useState(false);
  const [willClose, setWillClose] = useState(false);
  useEffect(() => () => cancelDrag.current?.(), []);
  useEffect(() => { if (!wide || !previewOpen || !enabled) cancelDrag.current?.(); }, [wide, previewOpen, enabled]);
  function startDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || !groupRef.current || !groupElement.current) return;
    cancelDrag.current?.();
    const handle = event.currentTarget;
    const pointerId = event.pointerId;
    const startX = event.clientX;
    const original = groupRef.current.getLayout();
    let close = false;
    let finished = false;
    handle.setPointerCapture(pointerId);
    setDragging(true);
    function move(event: PointerEvent) {
      if (event.pointerId !== pointerId) return;
      const bounds = groupElement.current?.getBoundingClientRect();
      close = Boolean(onPreviewClose && bounds && Math.abs(event.clientX - startX) > 3 && event.clientX > bounds.left + bounds.width * .8);
      setWillClose(close);
    }
    function finish(cancel: boolean) {
      if (finished) return;
      finished = true;
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", up, true);
      window.removeEventListener("pointercancel", abort, true);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("blur", abort);
      handle.removeEventListener("lostpointercapture", abort);
      cancelDrag.current = null;
      if (cancel) handle.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true, pointerId }));
      if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
      if (cancel) groupRef.current?.setLayout(original);
      else if (close) onPreviewClose?.();
      setDragging(false);
      setWillClose(false);
    }
    function up(event: PointerEvent) { if (event.pointerId === pointerId) { move(event); finish(false); } }
    function abort() { finish(true); }
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); finish(true); }
    }
    cancelDrag.current = abort;
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
    window.addEventListener("pointercancel", abort, true);
    window.addEventListener("keydown", key, true);
    window.addEventListener("blur", abort);
    handle.addEventListener("lostpointercapture", abort);
  }
  const open = Boolean(preview) && previewOpen;
  const [present, setPresent] = useState(open);
  useEffect(() => {
    if (open) { setPresent(true); return; }
    // Keep the viewer in place until the closing transition has finished.
    const timer = window.setTimeout(() => setPresent(false), 240);
    return () => window.clearTimeout(timer);
  }, [open]);
  useEffect(() => {
    if (!enabled || !wide || !preview) return;
    // Panel registration must finish before applying a layout.
    const frame = requestAnimationFrame(() => groupRef.current?.setLayout(open ? { list: 50, preview: 50 } : { list: 100, preview: 0 }));
    return () => cancelAnimationFrame(frame);
  }, [enabled, wide, Boolean(preview), open, groupRef]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(min-width: 1400px)");
    const changed = () => { if (!document.fullscreenElement) setWide(media.matches); };
    media.addEventListener("change", changed);
    document.addEventListener("fullscreenchange", changed);
    return () => { media.removeEventListener("change", changed); document.removeEventListener("fullscreenchange", changed); };
  }, []);
  function save(next: Preferences) {
    setPreferences(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Storage may be unavailable; resizing still works. */ }
  }
  if (!enabled) return <>{categories?.(false, () => undefined)}{children}{preview}</>;
  return <div className={`library-shell${categories ? preferences.collapsed ? " categories-collapsed" : "" : " without-categories"}`}>
    {categories?.(preferences.collapsed, () => save({ ...preferences, collapsed: !preferences.collapsed }))}
    <Group id={`${module}-library-panels`} elementRef={groupElement} groupRef={groupRef} className="library-panels" data-preview-open={open} orientation="horizontal" style={{ overflow: "visible" }}
      defaultLayout={{ list: 50, preview: 50 }}>
      <Panel id="list" className="library-list-pane" minSize={wide && open ? 280 : 0} defaultSize="50%" style={{ overflow: "visible" }}>
        {children}
      </Panel>
      {wide && preview && <Separator className="library-resize-handle" disabled={!open} aria-hidden={!open} aria-label="调整文件列表和预览宽度" title="拖动调整；Esc 撤销；双击均分；拖过右侧八成后松开收起预览" onPointerDown={startDrag}><GripVertical size={14} aria-hidden="true" /></Separator>}
      {wide && preview && <Panel id="preview" className="library-preview-pane" minSize={open ? 340 : 0} maxSize={open ? "100%" : 0} defaultSize="50%" aria-hidden={!open} inert={!open} style={{ overflow: open ? "visible" : "hidden" }}>{(open || present) && preview}</Panel>}
    </Group>
    {!wide && (open || present) && preview}
    {dragging && createPortal(<div className="library-drag-shield"><span role="status">{willClose ? "松开收起预览 · Esc 撤销" : "拖动调整 · Esc 撤销"}</span></div>, document.body)}
  </div>;
}
