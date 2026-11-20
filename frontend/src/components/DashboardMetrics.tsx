import { useEffect } from "react";
import { animate, motion, useMotionValue, useReducedMotion, useTransform, type MotionValue } from "motion/react";
import { usePreference } from "../preferences";

const numberFormat = new Intl.NumberFormat("zh-CN");

// One clock keeps all counts and bars in step, including cached page visits.
export function useDashboardEntrance(ready: boolean) {
  const systemReducedMotion = useReducedMotion();
  const reduceMotion = usePreference("reduceMotion") === "true" || systemReducedMotion;
  const progress = useMotionValue(reduceMotion ? 1 : 0);

  useEffect(() => {
    if (!ready) return;
    if (reduceMotion) { progress.set(1); return; }
    const animation = animate(progress, 1, { duration: 1, ease: "easeOut" });
    return () => animation.stop();
  }, [ready, reduceMotion, progress]);

  return progress;
}

export function DashboardNumber({ value, progress }: { value: number; progress: MotionValue<number> }) {
  const formatted = useTransform(progress, (latest) => numberFormat.format(Math.round(value * latest)));
  return <strong className="dashboard-number"><span className="sr-only">{numberFormat.format(value)}</span><motion.span aria-hidden="true">{formatted}</motion.span></strong>;
}
