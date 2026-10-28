import { useEffect, useState } from "react";

export function useReauthStatus(until?: string | null) {
  const parsed = Date.parse(until ?? "");
  const deadline = Number.isFinite(parsed) ? parsed : 0;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const timer = window.setInterval(update, 1000);
    window.addEventListener("focus", update);
    window.addEventListener("pageshow", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      window.removeEventListener("pageshow", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [deadline]);
  return {
    reauthenticated: deadline > now,
    expired: deadline > 0 && deadline <= now,
    remainingSeconds: Math.max(0, Math.ceil((deadline - now) / 1000)),
    // Action handlers must check wall-clock time even between display ticks.
    isCurrent: () => deadline > Date.now(),
  };
}
