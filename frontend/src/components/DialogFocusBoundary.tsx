import type { ReactNode } from "react";

export function DialogFocusBoundary({ children }: { children: ReactNode }) {
  return <div className="dialog-focus-boundary" onKeyDown={(event) => {
    if (event.key !== "Tab") return;
    const controls = [...event.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled):not([tabindex='-1']), select:not(:disabled), textarea:not(:disabled), summary, a[href]")]
      .filter((element) => element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls.at(-1);
    if (first && last && document.activeElement === (event.shiftKey ? first : last)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  }}>{children}</div>;
}
