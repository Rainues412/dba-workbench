import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

const modules = [
  ["scripts", "脚本库"], ["articles", "知识库"], ["resources", "资源中心"],
  ["tasks", "任务管理"], ["customers", "客户项目"],
] as const;
type Results = Record<string, { id: number; title?: string; name?: string }[]>;

export function GlobalSearch() {
  const navigate = useNavigate();
  const titleId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); setOpen((value) => !value);
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    return () => trigger.current?.focus();
  }, [open]);
  useEffect(() => {
    setResults({}); setError("");
    if (!open || !query.trim()) { setLoading(false); return; }
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      void api<Results>(`/api/search/?${new URLSearchParams({ q: query.trim(), limit: "10" })}`, { signal: controller.signal })
        .then((data) => { if (active) setResults(data); })
        .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "搜索失败，请重试"); })
        .finally(() => { if (active) setLoading(false); });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [open, query]);

  const count = modules.reduce((sum, [key]) => sum + (results[key]?.length ?? 0), 0);
  return <>
    <button ref={trigger} className="button global-search-trigger" onClick={() => setOpen(true)} aria-label="全局搜索（Ctrl+K）"><Search size={17} /><span>搜索</span><kbd>Ctrl K</kbd></button>
    {open && createPortal(<div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section ref={dialog} className="modal global-search-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
        if (event.key === "Tab") {
          const controls = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input");
          const first = controls?.[0]; const last = controls?.[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          const controls = [input.current, ...Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>(".global-search-result") ?? [])].filter((item): item is HTMLInputElement | HTMLButtonElement => !!item);
          const index = controls.indexOf(document.activeElement as HTMLInputElement | HTMLButtonElement);
          if (index >= 0) { event.preventDefault(); controls[(index + (event.key === "ArrowDown" ? 1 : controls.length - 1)) % controls.length]?.focus(); }
        }
      }}>
        <div className="modal-header"><h2 id={titleId}>全局搜索</h2><button className="icon-button" onClick={() => setOpen(false)} aria-label="关闭搜索"><X size={19} /></button></div>
        <label className="search-field"><Search size={17} /><span className="sr-only">跨模块搜索关键词</span><input ref={input} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索脚本、文档、资源、任务和客户" /></label>
        <p className="muted">保险箱内容仅在解锁后的保险箱内搜索。</p>
        <div className="global-search-results" aria-live="polite" aria-busy={loading}>
          {loading ? <p role="status">搜索中…</p> : error ? <div className="alert error" role="alert">{error}</div> : !query.trim() ? <p className="muted">输入关键词快速跳转到记录。</p> : !count ? <p>没有匹配记录</p> : modules.map(([key, label]) => !!results[key]?.length && <section key={key} aria-label={label}><h3>{label}</h3>{results[key].map((result) => <button className="button global-search-result" key={result.id} onClick={() => { setOpen(false); navigate(`/${key}?record=${result.id}`); }}>{result.title || result.name || `记录 ${result.id}`}</button>)}{results[key].length === 10 && <small className="muted">每个模块最多显示 10 条，请细化关键词。</small>}</section>)}
        </div>
      </section>
    </div>, document.body)}
  </>;
}
