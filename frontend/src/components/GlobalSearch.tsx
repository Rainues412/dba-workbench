import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { SearchHighlight } from "./SearchHighlight";

const modules = [
  ["scripts", "脚本库"], ["articles", "知识库"], ["resources", "资源中心"],
  ["customers", "客户项目"],
] as const;
type ModuleKey = (typeof modules)[number][0];
type SearchRecord = { id: number; title?: string; name?: string };
type Results = Partial<Record<ModuleKey, SearchRecord[]>>;
type SearchItem = SearchRecord & { module: ModuleKey; moduleLabel: string };

export function GlobalSearch() {
  const navigate = useNavigate();
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [focused, setFocused] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);

  const items = useMemo(() => modules.flatMap(([module, moduleLabel]) =>
    (results[module] ?? []).map((record) => ({ ...record, module, moduleLabel }))), [results]);
  const open = focused && !!query.trim();

  function choose(item: SearchItem) {
    setFocused(false);
    input.current?.blur();
    const target = item.module === "articles" || item.module === "scripts" ? "preview" : "record";
    navigate(`/${item.module}?${target}=${item.id}`, { state: { previewSearch: target === "preview" } });
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); input.current?.focus();
      }
    }
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setFocused(false);
    }
    window.addEventListener("keydown", shortcut);
    document.addEventListener("pointerdown", outside);
    return () => {
      window.removeEventListener("keydown", shortcut);
      document.removeEventListener("pointerdown", outside);
    };
  }, []);

  useEffect(() => {
    setResults({}); setError(""); setActiveIndex(-1);
    if (!query.trim()) { setLoading(false); return; }
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      void api<Results>(`/api/search/?${new URLSearchParams({ q: query.trim(), limit: "0" })}`, { signal: controller.signal })
        .then((data) => { if (active) setResults(data); })
        .catch((reason: unknown) => { if (active && !(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "搜索失败，请重试"); })
        .finally(() => { if (active) setLoading(false); });
    }, 180);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  useEffect(() => {
    const item = itemRefs.current[activeIndex];
    if (activeIndex >= 0 && typeof item?.scrollIntoView === "function") item.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return <div ref={root} className="global-search">
    <label className="global-search-box">
      <Search size={17} aria-hidden="true" />
      <span className="sr-only">跨模块搜索关键词</span>
      <input
        ref={input}
        value={query}
        onFocus={() => setFocused(true)}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); setFocused(false); input.current?.blur(); return; }
          if (!items.length || (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Enter")) return;
          event.preventDefault();
          if (event.key === "Enter") { if (activeIndex >= 0) choose(items[activeIndex]); return; }
          const step = event.key === "ArrowDown" ? 1 : -1;
          setActiveIndex((current) => current < 0 ? (step > 0 ? 0 : items.length - 1) : (current + step + items.length) % items.length);
        }}
        placeholder="全局搜索标题"
        role="combobox"
        aria-label="跨模块搜索关键词"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
      />
      <kbd>Ctrl K</kbd>
    </label>
    {open && <div id={listId} className="global-search-dropdown" role="listbox" aria-label="全局搜索结果" aria-busy={loading}>
      {loading ? <div className="global-search-state" role="status">搜索中…</div>
        : error ? <div className="global-search-state error-text" role="alert">{error}</div>
        : !items.length ? <div className="global-search-state">没有匹配记录</div>
        : items.map((item, index) => {
          const displayTitle = item.title || item.name || `记录 ${item.id}`;
          return <button
            ref={(node) => { itemRefs.current[index] = node; }}
            id={`${listId}-${index}`}
            className={`global-search-result${activeIndex === index ? " is-active" : ""}`}
            key={`${item.module}-${item.id}`}
            role="option"
            aria-label={`${displayTitle} ${item.moduleLabel}`}
            aria-selected={activeIndex === index}
            onMouseEnter={() => setActiveIndex(index)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => choose(item)}
          >
            <span className="global-search-result-title" title={displayTitle}><SearchHighlight text={displayTitle} query={query} /></span>
            <span className="global-search-result-module">{item.moduleLabel}</span>
          </button>})}
    </div>}
  </div>;
}
