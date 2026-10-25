import { useId, type ReactNode } from "react";
import { LayoutGroup, MotionConfig, motion } from "motion/react";

export const selectionSpring = { type: "spring", stiffness: 420, damping: 29, mass: .8 } as const;

export function SelectionMotion({ children }: { children: ReactNode }) {
  const id = useId();
  return <MotionConfig reducedMotion="user"><LayoutGroup id={id}>{children}</LayoutGroup></MotionConfig>;
}

export function SelectionIndicator({ className, radius = 8 }: { className: string; radius?: number }) {
  return <motion.span className={`selection-indicator ${className}`} aria-hidden="true" layout layoutId="selection" initial={false} transition={selectionSpring} style={{ borderRadius: radius }} />;
}
