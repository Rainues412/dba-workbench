import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { savePreference, usePreference } from "../preferences";

export function ScriptCodePreview({ text }: { text: string }) {
  const fontSize = usePreference("codeSize");
  const wrap = usePreference("codeWrap") === "true";
  const showNumbers = usePreference("lineNumbers") === "true";
  const [finding, setFinding] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const match = useRef<HTMLElement>(null);
  const matches = useMemo(() => {
    if (!finding || !query) return [];
    const positions: number[] = [];
    const expression = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
    for (const result of text.matchAll(expression)) positions.push(result.index);
    return positions;
  }, [finding, query, text]);
  const matchStart = matches[active] ?? matches[0];
  const lines = useMemo(() => text.split("\n"), [text]);
  const numbered = showNumbers && lines.length <= 10_000;
  const size = Math.min(18, Math.max(12, Number(fontSize) || 14));

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      const preview = root.current;
      if (!preview?.getClientRects().length || event.defaultPrevented) return;
      const openDialogs = document.querySelectorAll("dialog[open], [role=dialog][aria-modal=true]");
      const modal = openDialogs[openDialogs.length - 1];
      if (modal && !modal.contains(preview)) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setFinding(true);
        field.current?.focus();
      } else if (finding && event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setFinding(false);
        setQuery("");
      }
    }
    window.addEventListener("keydown", shortcut, true);
    return () => window.removeEventListener("keydown", shortcut, true);
  }, [finding]);
  useEffect(() => { if (finding) field.current?.focus(); }, [finding]);
  useEffect(() => { match.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }, [matchStart]);

  function renderText(value: string, offset: number) {
    if (matchStart === undefined || matchStart < offset || matchStart >= offset + value.length) return value;
    const start = matchStart - offset;
    return <>{value.slice(0, start)}<mark ref={match}>{value.slice(start, start + query.length)}</mark>{value.slice(start + query.length)}</>;
  }

  let offset = 0;
  return <div ref={root} className="script-code-viewer">
    <div className="script-code-controls">
      <select aria-label="代码字号" value={fontSize} onChange={(event) => savePreference("codeSize", event.target.value)}>
        <option value="0">默认 14 px</option>{[12, 13, 14, 15, 16, 17, 18].map((value) => <option key={value} value={value}>{value} px</option>)}
      </select>
      <button type="button" className="button small" aria-pressed={wrap} onClick={() => savePreference("codeWrap", String(!wrap))}>自动换行</button>
      <button type="button" className="button small" onClick={() => setFinding(true)}><Search size={14} />查找</button>
    </div>
    {finding && <div className="script-code-find">
      <input ref={field} aria-label="代码内查找" value={query} placeholder="代码内查找" onChange={(event) => { setQuery(event.target.value); setActive(0); }}
        onKeyDown={(event) => {
          if (event.key !== "Enter" || !matches.length) return;
          event.preventDefault();
          setActive((current) => (current + (event.shiftKey ? -1 : 1) + matches.length) % matches.length);
        }} />
      <span aria-live="polite">{query && (matches.length ? `${active < matches.length ? active + 1 : 1} / ${matches.length}` : "无匹配")}</span>
      <button type="button" className="icon-button" aria-label="关闭代码查找" onClick={() => { setFinding(false); setQuery(""); }}><X size={16} /></button>
    </div>}
    <pre className={`library-code${wrap ? " code-wrap" : ""}${numbered ? " code-numbered" : ""}`} style={{ fontSize: `${size}px` }}><code>
      {numbered ? lines.map((line, index) => {
        const content = renderText(line, offset);
        offset += line.length + 1;
        return <span className="script-code-line" key={index}><span aria-hidden="true" className="script-code-number">{index + 1}</span><span>{content || " "}</span></span>;
      }) : renderText(text, 0)}
    </code></pre>
  </div>;
}
