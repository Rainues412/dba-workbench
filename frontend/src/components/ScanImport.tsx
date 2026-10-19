import { useEffect, useId, useRef, useState } from "react";
import { FolderOpen, Import, X } from "lucide-react";
import { api, ApiError, jsonBody } from "../api/client";

type Module = "scripts" | "articles" | "resources";
type Proposal = {
  kind: "script" | "article" | "resource"; name: string; path: string; size_mb?: number;
  db_type?: string; category?: string; res_kind?: string; tags?: string[];
};
const kinds = { scripts: "script", articles: "article", resources: "resource" } as const;
const labels = { scripts: "脚本", articles: "文档", resources: "资源" } as const;

export function ScanImport({ module, onImported }: { module: Module; onImported?: () => void | Promise<void> }) {
  const titleId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [items, setItems] = useState<Proposal[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"" | "picker" | "scan" | "import">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    return () => { request.current?.abort(); trigger.current?.focus(); };
  }, [open]);
  function close() {
    if (busy === "import" || busy === "picker") return;
    request.current?.abort(); setBusy(""); setOpen(false);
  }
  function changePath(value: string) { setPath(value); setItems([]); setSelected(new Set()); setError(""); setNotice(""); }
  function failure(reason: unknown) {
    const detail = reason instanceof Error ? reason.message : "请求失败，请重试";
    setError(reason instanceof ApiError && reason.status === 403 ? `本机目录操作未获许可：${detail}。请由管理员配置允许目录及对应扫描或目录选择权限；不会自动扩大权限。` : detail);
  }
  async function run(action: "picker" | "scan" | "import") {
    const controller = new AbortController(); request.current = controller;
    setBusy(action); setError(""); setNotice("");
    try {
      if (action === "picker") {
        const picked = await api<{ ok: boolean; path: string }>("/api/launcher/pick-folder", { method: "POST", body: jsonBody({ title: `选择${labels[module]}导入目录`, initial_dir: path.trim() }), signal: controller.signal });
        if (picked.ok) changePath(picked.path);
      } else if (action === "scan") {
        setItems([]); setSelected(new Set());
        const result = await api<{ items: Proposal[]; proposed: number }>("/api/scan/run", { method: "POST", body: jsonBody({ paths: [path.trim()] }), signal: controller.signal });
        if (controller.signal.aborted) return;
        const matching = result.items.filter((item) => item.kind === kinds[module]);
        setItems(matching); setSelected(new Set(matching.map((item) => item.path)));
        setNotice(`发现 ${result.proposed} 个未入库文件，其中 ${matching.length} 个${labels[module]}可导入当前模块。已有路径不会重复导入。`);
      } else {
        const result = await api<{ imported: Record<string, number> }>("/api/scan/commit", { method: "POST", body: jsonBody({ items: items.filter((item) => selected.has(item.path)) }), signal: controller.signal });
        setItems((current) => current.filter((item) => !selected.has(item.path))); setSelected(new Set());
        setNotice(`已导入 ${result.imported[kinds[module]] ?? 0} 条，跳过重复 ${result.imported.skipped ?? 0} 条。`);
        try { await onImported?.(); }
        catch { setError("导入已成功，但列表刷新失败，请关闭后刷新页面；不要重复提交。"); }
      }
    } catch (reason) { if (!controller.signal.aborted) failure(reason); }
    finally { if (request.current === controller) setBusy(""); }
  }

  return <>
    <button ref={trigger} className="button" onClick={() => setOpen(true)}><Import size={17} />目录批量导入</button>
    {open && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
      <section ref={dialog} className="modal scan-import-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); close(); }
        if (event.key === "Tab") {
          const controls = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)");
          const first = controls?.[0]; const last = controls?.[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      }}>
        <div className="modal-header"><h2 id={titleId}>批量导入{labels[module]}</h2><button className="icon-button" aria-label="关闭批量导入" disabled={busy === "import" || busy === "picker"} onClick={close}><X size={19} /></button></div>
        <p className="muted">仅扫描管理员允许的本机目录；只建立索引，不移动文件、不执行脚本。预览后勾选确认才会写入。</p>
        <div className="form-grid"><label className="full">扫描目录<input ref={input} value={path} onChange={(event) => changePath(event.target.value)} placeholder="输入已获许可的绝对目录路径" disabled={!!busy} /></label><div className="button-row full"><button className="button" disabled={!!busy} onClick={() => void run("picker")}><FolderOpen size={17} />选择目录</button><button className="button primary" disabled={!!busy || !path.trim()} onClick={() => void run("scan")}>{busy === "scan" ? "扫描中…" : "扫描预览"}</button></div></div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {notice && <p role="status">{notice}</p>}
        {!!items.length && <div className="scan-preview"><label><input type="checkbox" checked={selected.size === items.length} disabled={!!busy} onChange={(event) => setSelected(new Set(event.target.checked ? items.map((item) => item.path) : []))} />全选（已选 {selected.size} / {items.length}）</label>{items.map((item) => <label key={item.path} className="scan-preview-item"><input type="checkbox" aria-label={`导入：${item.name}`} checked={selected.has(item.path)} disabled={!!busy} onChange={(event) => setSelected((current) => { const next = new Set(current); if (event.target.checked) next.add(item.path); else next.delete(item.path); return next; })} /><span><strong>{item.name}</strong><small>{item.db_type || "其他"}{item.category ? ` / ${item.category}` : ""}</small><small className="muted">{item.path}</small></span></label>)}</div>}
        <div className="modal-actions"><button className="button" onClick={close} disabled={busy === "import" || busy === "picker"}>关闭</button><button className="button primary" disabled={!!busy || !selected.size} onClick={() => void run("import")}>{busy === "import" ? "导入中…" : `导入所选（${selected.size}）`}</button></div>
      </section>
    </div>}
  </>;
}
