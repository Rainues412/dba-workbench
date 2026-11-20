import { useEffect, useRef, useState } from "react";
import { Command, Search, X, type LucideIcon } from "lucide-react";
import { AppDialog } from "./AppDialog";

export type WorkbenchCommand = { title: string; section: string; icon: LucideIcon; run: () => void };

export function WorkbenchCommands({ commands, onClose }: { commands: WorkbenchCommand[]; onClose: () => void }) {
  const results = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const visible = commands.filter(({ title, section }) => `${title} ${section}`.toLowerCase().includes(query.trim().toLowerCase()));
  useEffect(() => {
    results.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  function run(command?: WorkbenchCommand) {
    if (!command) return;
    onClose();
    window.requestAnimationFrame(command.run);
  }
  return <AppDialog className="command-palette" labelledBy="workbench-command-title" onClose={onClose} initialFocus={search}>
    <header><h2 id="workbench-command-title"><Command size={14} /> 快捷操作</h2><button type="button" aria-label="关闭快捷操作" onClick={onClose}><X /></button></header>
    <label className="command-search"><Search /><input ref={search} aria-label="搜索快捷操作" placeholder="输入命令" value={query}
      onChange={(event) => { setQuery(event.target.value); setSelected(0); }}
      onKeyDown={(event) => {
        if (!visible.length) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          setSelected((index) => (index + (event.key === "ArrowDown" ? 1 : -1) + visible.length) % visible.length);
        } else if (event.key === "Enter") {
          event.preventDefault(); run(visible[selected]);
        }
      }} /></label>
    <div ref={results} className="command-results" role="listbox" aria-label="可用操作">
      {visible.map((command, index) => <button type="button" role="option" aria-selected={selected === index} key={command.title}
        onPointerMove={() => setSelected(index)} onClick={() => run(command)}><command.icon /><span><strong>{command.title}</strong></span></button>)}
      {!visible.length && <div className="command-empty" role="status">没有匹配的快捷操作。</div>}
    </div>
    <footer><span><kbd>↑</kbd><kbd>↓</kbd>选择</span><span><kbd>Enter</kbd>运行</span><span><kbd>Esc</kbd>关闭</span></footer>
  </AppDialog>;
}
