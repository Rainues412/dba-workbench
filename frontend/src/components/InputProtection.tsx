import { useRef, type ReactNode } from "react";

// Capture before child shortcuts, including React portals. Never cancel the
// native composing key: the IME still needs it to select a candidate.
export function InputProtection({ children }: { children: ReactNode }) {
  const states = useRef(new WeakMap<EventTarget, { composing: boolean; ended: number }>());
  return <div style={{ display: "contents" }}
    onCompositionStartCapture={(event) => states.current.set(event.target, { composing: true, ended: -Infinity })}
    onCompositionEndCapture={(event) => states.current.set(event.target, { composing: false, ended: performance.now() })}
    onKeyDownCapture={(event) => {
      const state = states.current.get(event.target);
      const composing = state?.composing || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229;
      if (composing && ["Enter", "ArrowUp", "ArrowDown", "Escape"].includes(event.key)) {
        event.stopPropagation();
      } else if (event.key === "Enter" && state && performance.now() - state.ended < 500) {
        event.preventDefault();
        event.stopPropagation();
      }
    }}
    onSubmitCapture={(event) => {
      const state = document.activeElement && states.current.get(document.activeElement);
      if (state?.composing) { event.preventDefault(); event.stopPropagation(); }
    }}
  >{children}</div>;
}
