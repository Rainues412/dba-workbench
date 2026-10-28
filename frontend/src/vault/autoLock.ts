export const VAULT_IDLE_TIMEOUT_MS = 15 * 60 * 1000;

export function startVaultAutoLock(
  onLock: (reason: "idle") => void,
  timeout = VAULT_IDLE_TIMEOUT_MS,
  windowTarget: Window = window,
  documentTarget: Document = document,
) {
  let deadline = Date.now() + timeout;
  let locked = false;
  const check = () => {
    if (!locked && Date.now() >= deadline) { locked = true; onLock("idle"); }
  };
  let timer = windowTarget.setTimeout(check, timeout);
  const reset = () => {
    check();
    if (locked) return;
    deadline = Date.now() + timeout;
    windowTarget.clearTimeout(timer);
    timer = windowTarget.setTimeout(check, timeout);
  };
  const visible = () => {
    if (documentTarget.visibilityState === "visible") check();
  };
  windowTarget.addEventListener("pointerdown", reset, { passive: true });
  windowTarget.addEventListener("keydown", reset);
  windowTarget.addEventListener("focus", check);
  documentTarget.addEventListener("visibilitychange", visible);
  return () => {
    windowTarget.clearTimeout(timer);
    windowTarget.removeEventListener("pointerdown", reset);
    windowTarget.removeEventListener("keydown", reset);
    windowTarget.removeEventListener("focus", check);
    documentTarget.removeEventListener("visibilitychange", visible);
  };
}
