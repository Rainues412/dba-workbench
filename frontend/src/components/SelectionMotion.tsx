import { useId, type ReactNode } from "react";
import { LayoutGroup, MotionConfig, motion, type Transition } from "motion/react";
import { usePreference } from "../preferences";

export const selectionSpring = { type: "spring", stiffness: 420, damping: 29, mass: .8 } as const;

export function SelectionMotion({ children }: { children: ReactNode }) {
  const id = useId();
  const reduceMotion = usePreference("reduceMotion") === "true";
  return <MotionConfig reducedMotion={reduceMotion ? "always" : "user"}><LayoutGroup id={id}>{children}</LayoutGroup></MotionConfig>;
}

export function SelectionIndicator({ className, radius = 8, transition = selectionSpring }: { className: string; radius?: number | string; transition?: Transition }) {
  return <motion.span className={`selection-indicator ${className}`} aria-hidden="true" layout layoutId="selection" initial={false} transition={transition} style={{ borderRadius: radius }} />;
}
