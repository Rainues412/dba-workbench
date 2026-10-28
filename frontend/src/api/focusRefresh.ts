// TanStack Query owns stale-query selection, request deduplication and reconnects.
export function listenForAppFocus(onFocus: () => void) {
  const listener = () => onFocus();
  window.addEventListener("focus", listener);
  window.addEventListener("pageshow", listener);
  window.addEventListener("visibilitychange", listener);
  return () => {
    window.removeEventListener("focus", listener);
    window.removeEventListener("pageshow", listener);
    window.removeEventListener("visibilitychange", listener);
  };
}
