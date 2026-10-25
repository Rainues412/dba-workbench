import { useEffect, useState, type RefObject } from "react";
import { MotionConfig, motion } from "motion/react";
import { selectionSpring } from "./SelectionMotion";

// Tocbot owns its links and active-heading detection. Observe that output only;
// Motion handles the same spring used by the React navigation controls.
export function OutlineIndicator({ container }: { container: RefObject<HTMLDivElement | null> }) {
  const [bounds, setBounds] = useState<{ x: number; y: number; width: number; height: number } | null>(null);
  useEffect(() => {
    const root = container.current;
    if (!root) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const active = root.querySelector<HTMLElement>(".is-active-link");
        if (!active || !active.getClientRects().length) { setBounds(null); return; }
        const origin = root.getBoundingClientRect();
        const target = active.getBoundingClientRect();
        setBounds({ x: target.x - origin.x, y: target.y - origin.y, width: target.width, height: target.height });
      });
    };
    const changes = new MutationObserver(update);
    changes.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
    const sizes = new ResizeObserver(update);
    sizes.observe(root);
    update();
    return () => { changes.disconnect(); sizes.disconnect(); cancelAnimationFrame(frame); };
  }, [container]);
  return bounds && <MotionConfig reducedMotion="user"><motion.span aria-hidden="true" className="toc-active-indicator" initial={false} animate={bounds} transition={selectionSpring} /></MotionConfig>;
}
