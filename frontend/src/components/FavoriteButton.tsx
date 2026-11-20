import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { Star } from "lucide-react";

const particles = Array.from({ length: 5 }, (_, index) => {
  const angle = (index * 72 - 90) * Math.PI / 180;
  return {
    "--burst-x": `${Math.cos(angle) * 22}px`,
    "--burst-y": `${Math.sin(angle) * 22}px`,
    "--burst-start-x": `${Math.cos(angle) * 7}px`,
    "--burst-start-y": `${Math.sin(angle) * 7}px`,
  } as CSSProperties;
});

export function FavoriteButton({ active, disabled, onToggle }: {
  active: boolean;
  disabled: boolean;
  onToggle: () => Promise<void>;
}) {
  const previous = useRef(active);
  const [burst, setBurst] = useState(false);
  const [busy, setBusy] = useState(false);
  useLayoutEffect(() => {
    if (active !== previous.current) {
      setBurst(active && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
      previous.current = active;
    }
  }, [active]);

  return <button type="button" className={`icon-button favorite-button${active ? " is-favorite" : ""}${burst ? " is-bursting" : ""}`} aria-label={active ? "取消收藏" : "收藏"} aria-pressed={active} title={active ? "取消收藏" : "收藏"} disabled={disabled || busy} onClick={async () => {
    setBusy(true);
    try { await onToggle(); }
    finally { setBusy(false); }
  }}>
    <Star className="favorite-star" size={16} fill={active ? "currentColor" : "none"} aria-hidden="true" onAnimationEnd={() => setBurst(false)} />
    {burst && <span className="favorite-particles" aria-hidden="true">{particles.map((style, index) => <span key={index} style={style} />)}</span>}
  </button>;
}
