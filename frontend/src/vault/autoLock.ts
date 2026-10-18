export const VAULT_IDLE_TIMEOUT_MS = 5 * 60 * 1000;

export function startVaultAutoLock(
  onLock: (reason: "idle" | "hidden") => void,
  timeout = VAULT_IDLE_TIMEOUT_MS,
  windowTarget: Window = window,
  documentTarget: Document = document,
) {
  let timer = windowTarget.setTimeout(() => onLock("idle"), timeout);
  const reset = () => {
    windowTarget.clearTimeout(timer);
    timer = windowTarget.setTimeout(() => onLock("idle"), timeout);
  };
  const hidden = () => {
    if (documentTarget.visibilityState === "hidden") onLock("hidden");
  };
  windowTarget.addEventListener("pointerdown", reset, { passive: true });
  windowTarget.addEventListener("keydown", reset);
  documentTarget.addEventListener("visibilitychange", hidden);
  return () => {
    windowTarget.clearTimeout(timer);
    windowTarget.removeEventListener("pointerdown", reset);
    windowTarget.removeEventListener("keydown", reset);
    documentTarget.removeEventListener("visibilitychange", hidden);
  };
}
