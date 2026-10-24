import { useEffect, useState, type ReactNode } from "react";
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
export function LibraryLayout({ module, enabled, categories, preview, previewOpen = true, children }: {
  module: string;
  enabled: boolean;
  categories?: (collapsed: boolean, toggle: () => void) => ReactNode;
  preview?: ReactNode;
  previewOpen?: boolean;
  children: ReactNode;
}) {
  const storageKey = `dba-library-layout:${module}`;
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey));
  const [wide, setWide] = useState(() => typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 1400px)").matches);
  const groupRef = useGroupRef();
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
    // Panel registration must finish before applying a layout (e.g. after closing the editor).
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
    <Group id={`${module}-library-panels`} groupRef={groupRef} className="library-panels" data-preview-open={open} orientation="horizontal" style={{ overflow: "visible" }}
      defaultLayout={{ list: 50, preview: 50 }}>
      <Panel id="list" className="library-list-pane" minSize={wide && open ? 280 : 0} defaultSize="50%" style={{ overflow: "visible" }}>
        {children}
      </Panel>
      {wide && preview && <Separator className="library-resize-handle" disabled={!open} aria-hidden={!open} aria-label="调整文件列表和预览宽度" title="拖动调整列表和预览宽度；方向键微调，双击恢复默认比例" onPointerDown={(event) => {
        // Capture immediately so the first movement into an embedded viewer is not lost.
        if (event.button === 0) event.currentTarget.setPointerCapture(event.pointerId);
      }}><GripVertical size={14} aria-hidden="true" /></Separator>}
      {wide && preview && <Panel id="preview" className="library-preview-pane" minSize={open ? 340 : 0} maxSize={open ? "100%" : 0} defaultSize="50%" aria-hidden={!open} inert={!open} style={{ overflow: open ? "visible" : "hidden" }}>{(open || present) && preview}</Panel>}
    </Group>
    {!wide && (open || present) && preview}
  </div>;
}
