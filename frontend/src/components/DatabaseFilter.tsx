import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Database } from "lucide-react";
import { DatabaseLabel } from "./DatabaseLabel";

export function DatabaseFilter({ value, names, counts, total, onChange }: {
  value: string;
  names: string[];
  counts: Map<string, number>;
  total: number;
  onChange: (value: string) => void;
}) {
  const listId = useId();
  const labelId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const search = useRef({ text: "", time: 0 });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<CSSProperties>({});
  const options = ["", ...names];
  const selected = Math.max(0, options.indexOf(value));
  const count = (name: string) => name ? counts.get(name) ?? 0 : total;
  const nameLabel = (name: string) => name || "全部数据库";
  const optionId = (index: number) => `${listId}-${index}`;

  function show(index = selected) { setActive(index); setOpen(true); }
  function choose(index: number) {
    if (options[index] === undefined) return;
    onChange(options[index]);
    setOpen(false);
    trigger.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const { key } = event;
    if (key === "ArrowDown" || key === "ArrowUp" || key === "Home" || key === "End") {
      event.preventDefault();
      const next = key === "Home" ? 0 : key === "End" ? options.length - 1
        : !open ? selected : Math.max(0, Math.min(options.length - 1, active + (key === "ArrowDown" ? 1 : -1)));
      show(next);
    } else if (key === "Enter" || key === " ") {
      event.preventDefault();
      if (open) choose(active); else show();
    } else if (key === "Escape" && open) {
      event.preventDefault(); event.stopPropagation(); setOpen(false);
    } else if (key === "Tab" && open) {
      onChange(options[active]); setOpen(false);
    } else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      const now = Date.now();
      const previous = now - search.current.time < 700 ? search.current.text : "";
      const text = previous && [...previous].every((letter) => letter === key.toLowerCase()) ? key.toLowerCase() : previous + key.toLowerCase();
      search.current = { text, time: now };
      const start = open ? active : selected;
      const match = options.map((_, offset) => (start + 1 + offset) % options.length)
        .find((index) => nameLabel(options[index]).toLowerCase().startsWith(text));
      if (match !== undefined) show(match);
    }
  }
  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect) return;
      if (rect.bottom < 0 || rect.top > window.innerHeight) { setOpen(false); return; }
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upwards = below < 180 && above > below;
      const width = Math.min(Math.max(rect.width, 224), window.innerWidth - 16);
      setPosition({ position: "fixed", width, left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
        maxHeight: Math.max(60, Math.min(360, upwards ? above : below)),
        ...(upwards ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }) });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: Event) => {
      if (!trigger.current?.contains(event.target as Node) && !popup.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("focusin", closeOutside);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("focusin", closeOutside); };
  }, [open]);
  useEffect(() => {
    if (open) document.getElementById(optionId(active))?.scrollIntoView?.({ block: "nearest" });
  }, [open, active, listId]);

  function label(name: string) {
    return name ? <DatabaseLabel name={name} /> : <span className="database-filter-all"><Database size={17} aria-hidden="true" /><strong>全部数据库</strong></span>;
  }
  return <div className="library-database-select">
    <span id={labelId}>数据库</span>
    <button ref={trigger} type="button" role="combobox" aria-label="筛选数据库" aria-expanded={open}
      aria-haspopup="listbox" aria-controls={listId} aria-activedescendant={open ? optionId(active) : undefined}
      title={`${nameLabel(value)}（${count(value)}）`} className="database-filter-trigger"
      onClick={() => { if (open) setOpen(false); else show(); }} onKeyDown={keyDown}>
      {label(value)}<span className="database-filter-count">{count(value)}</span><ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && createPortal(<div ref={popup} id={listId} role="listbox" aria-labelledby={labelId} className="database-filter-popup" style={position}>
      {options.map((name, index) => <div key={name} id={optionId(index)} role="option" aria-selected={value === name}
        aria-label={`${nameLabel(name)}（${count(name)}）`} title={`${nameLabel(name)}（${count(name)}）`}
        className={`database-filter-option${active === index ? " active" : ""}`} onPointerMove={() => setActive(index)}
        onMouseDown={(event) => event.preventDefault()} onClick={() => choose(index)}>
        {label(name)}<span className="database-filter-count">{count(name)}</span><span className="database-filter-check">{value === name && <Check size={14} />}</span>
      </div>)}
    </div>, document.body)}
  </div>;
}
