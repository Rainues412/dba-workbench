import { type CSSProperties, type ReactNode, type RefObject, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { preferenceEvent } from "../preferences";

// Keep desktop window controls available while the dialog blocks the workspace.
export function AppDialog({ children, className, labelledBy, onClose, initialFocus, dimBackground = true }: {
  children: ReactNode;
  className: string;
  labelledBy: string;
  onClose: () => void;
  initialFocus?: RefObject<HTMLElement | null>;
  dimBackground?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const [bounds, setBounds] = useState({ top: 0, left: 0, right: 0, bottom: 0 });

  useLayoutEffect(() => {
    const controls = document.querySelector<HTMLElement>(".desktop-window-controls");
    if (!controls) return;
    function measure() {
      const currentControls = document.querySelector<HTMLElement>(".desktop-window-controls");
      if (!currentControls) return;
      const rect = currentControls.getBoundingClientRect();
      const titlebar = currentControls.closest(".topbar, .sidebar");
      setBounds({ top: titlebar?.getBoundingClientRect().bottom ?? rect.bottom, left: rect.left, right: rect.right, bottom: rect.bottom });
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(controls);
    let frame = 0;
    const layoutChanged = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    window.addEventListener(preferenceEvent, layoutChanged);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener(preferenceEvent, layoutChanged);
      window.removeEventListener("resize", measure);
    };
  }, []);

  useLayoutEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const node = dialog.current!;
    (initialFocus?.current ?? node.querySelector<HTMLElement>("[autofocus], input, button, select, textarea") ?? node).focus({ preventScroll: true });
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
      const open = [...document.querySelectorAll("dialog[open][data-app-dialog]")];
      if (open.at(-1) !== node) return;
      const focusedDialog = (document.activeElement as Element | null)?.closest("dialog[open]");
      if (focusedDialog && focusedDialog !== node) return;
      event.preventDefault();
      event.stopPropagation();
      close.current();
    }
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("keydown", escape);
      document.body.style.overflow = previousOverflow;
      previous?.focus({ preventScroll: true });
    };
  }, [initialFocus]);

  const style = {
    "--app-dialog-top": `${bounds.top}px`,
    "--window-controls-left": `${bounds.left}px`,
    "--window-controls-right": `${bounds.right}px`,
    "--window-controls-bottom": `${bounds.bottom}px`,
  } as CSSProperties;
  return createPortal(<div className="app-dialog-layer" data-desktop={bounds.top > 0 ? "" : undefined} style={style}>
    {dimBackground && <div className="app-dialog-shade" aria-hidden="true" />}
    <div className="app-dialog-dismiss" aria-hidden="true" onPointerDown={(event) => { if (event.button === 0) close.current(); }} />
    <dialog open data-app-dialog ref={dialog} className={className} aria-labelledby={labelledBy} tabIndex={-1}>
      {children}
    </dialog>
  </div>, document.body);
}
