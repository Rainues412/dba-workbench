import { useEffect, useId, useRef, useState } from "react";
import { FolderInput, FolderOpen, Import, ScanSearch, X } from "lucide-react";
import { api, ApiError, jsonBody } from "../api/client";

type Module = "scripts" | "articles" | "resources";
type Proposal = {
  kind: "script" | "article" | "resource"; name: string; path: string; size_mb?: number;
  db_type?: string; category?: string; res_kind?: string; tags?: string[];
};
const kinds = { scripts: "script", articles: "article", resources: "resource" } as const;
const labels = { scripts: "脚本", articles: "文档", resources: "资源" } as const;
const moduleNames = { scripts: "脚本库", articles: "知识库", resources: "资源中心" } as const;
type ScanResult = { items: Proposal[]; already_indexed?: Record<Proposal["kind"], number> };
type Preview = { items: Proposal[]; alreadyIndexed: number | undefined; elsewhere: string[] };
type Action = "picker" | "scan" | "import";

export function ScanImport({ module, onImported }: { module: Module; onImported?: () => void | Promise<void> }) {
  const titleId = useId();
  const directoryId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const scanButton = useRef<HTMLButtonElement>(null);
  const request = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Action | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const items = preview?.items ?? [];
  const label = labels[module];
  const kind = kinds[module];
  const closeDisabled = busy === "import" || busy === "picker";

  let scanSummary = "";
  let scanDetails = "";
  if (preview) {
    if (items.length) {
      scanSummary = `${items.length} 个${label}可导入`;
      if (preview.alreadyIndexed) scanDetails = `已入库 ${preview.alreadyIndexed} 个${label}。`;
    } else if (preview.alreadyIndexed === undefined) {
      scanSummary = `没有可导入的${label}`;
    } else {
      scanSummary = preview.alreadyIndexed
        ? `${preview.alreadyIndexed} 个${label}均已入库`
        : `扫描范围内没有支持的${label}`;
    }
    if (preview.elsewhere.length) scanDetails += `同一目录可在${preview.elsewhere.join("，在")}。`;
  }

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    return () => {
      request.current?.abort();
      request.current = null;
      trigger.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (open && !busy && document.activeElement === dialog.current) {
      const next = scanButton.current?.disabled ? input.current : scanButton.current;
      next?.focus();
    }
  }, [open, busy]);

  function close() {
    if (closeDisabled) return;
    request.current?.abort();
    request.current = null;
    setBusy(null);
    changePath(path);
    setOpen(false);
  }

  function changePath(value: string) {
    setPath(value);
    setPreview(null);
    setSelected(new Set());
    setError("");
    setNotice("");
  }

  function selectFile(path: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(path);
      else next.delete(path);
      return next;
    });
  }

  async function run(action: Action) {
    if (request.current) return;
    const controller = new AbortController();
    const { signal } = controller;
    request.current = controller;
    dialog.current?.focus();
    setBusy(action);
    setError("");
    if (action !== "picker") setNotice("");

    try {
      if (action === "picker") {
        const picked = await api<{ ok: boolean; path: string }>("/api/launcher/pick-folder", {
          method: "POST", body: jsonBody({ title: `选择${label}导入目录`, initial_dir: path.trim() }), signal,
        });
        if (!signal.aborted && picked.ok && picked.path !== path) changePath(picked.path);
      } else if (action === "scan") {
        setPreview(null);
        setSelected(new Set());
        const result = await api<ScanResult>("/api/scan/run", {
          method: "POST", body: jsonBody({ paths: [path.trim()] }), signal,
        });
        if (signal.aborted) return;
        const candidates: Proposal[] = [];
        const counts = { article: 0, script: 0, resource: 0 };
        for (const item of result.items) {
          counts[item.kind] += 1;
          if (item.kind === kind) candidates.push(item);
        }
        const elsewhere = (Object.keys(kinds) as Module[])
          .filter((key) => key !== module && counts[kinds[key]] > 0)
          .map((key) => `${moduleNames[key]}导入 ${counts[kinds[key]]} 项`);
        setPreview({ items: candidates, alreadyIndexed: result.already_indexed?.[kind], elsewhere });
        setSelected(new Set(candidates.map((item) => item.path)));
      } else {
        const result = await api<{ imported: Record<string, number> }>("/api/scan/commit", {
          method: "POST", body: jsonBody({ items: items.filter((item) => selected.has(item.path)) }), signal,
        });
        if (signal.aborted) return;
        const added = result.imported[kind] ?? 0;
        const skipped = result.imported.skipped ?? 0;
        setPreview((current) => current && {
          ...current,
          items: current.items.filter((item) => !selected.has(item.path)),
          alreadyIndexed: current.alreadyIndexed === undefined ? undefined : current.alreadyIndexed + added + skipped,
        });
        setSelected(new Set());
        setNotice(`已导入 ${added} 条，跳过重复 ${skipped} 条。`);
        try { await onImported?.(); }
        catch { if (!signal.aborted) setError("导入已成功，但列表刷新失败。请关闭弹窗后刷新页面。"); }
      }
    } catch (reason) {
      if (signal.aborted) return;
      const detail = reason instanceof Error ? reason.message : "请求失败，请重试";
      if (reason instanceof ApiError && reason.status === 403) {
        const hint = action === "picker" ? "可以手动输入已授权的目录路径。" : "可通过「选择目录」授权后重试。";
        setError(`本机目录操作未获许可（${detail}）。${hint}`);
      } else {
        setError(detail);
      }
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(null);
      }
    }
  }

  return <>
    <button ref={trigger} className="button" onClick={() => setOpen(true)}><Import size={17} />目录批量导入</button>
    {open && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
      <section ref={dialog} tabIndex={-1} className="modal scan-import-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); close(); }
        if (event.key === "Tab") {
          const controls = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)");
          const first = controls?.[0]; const last = controls?.[controls.length - 1];
          const atDialog = document.activeElement === dialog.current;
          if (atDialog || document.activeElement === (event.shiftKey ? first : last)) {
            event.preventDefault();
            (event.shiftKey ? last : first)?.focus();
          }
        }
      }}>
        <header className="modal-header">
          <span className="scan-import-icon"><FolderInput size={18} aria-hidden="true" /></span>
          <h2 id={titleId}>批量导入{label}</h2>
          <button type="button" className="icon-button scan-import-close" aria-label="关闭批量导入" title="关闭"
            disabled={closeDisabled} onClick={close}><X size={18} aria-hidden="true" /></button>
        </header>
        <div className="scan-import-body">
          <div className="scan-directory">
            <label htmlFor={directoryId}>扫描目录</label>
            <div className="scan-directory-controls">
              <input id={directoryId} ref={input} value={path} onChange={(event) => changePath(event.target.value)}
                placeholder="输入文件夹路径" title={path || undefined} spellCheck={false} disabled={!!busy} />
              <button type="button" className="button" disabled={!!busy} onClick={() => void run("picker")}>
                <FolderOpen size={16} aria-hidden="true" />{busy === "picker" ? "选择中…" : "选择目录"}
              </button>
              <button type="button" ref={scanButton} className={preview ? "button" : "button primary"}
                disabled={!!busy || !path.trim()} onClick={() => void run("scan")}>
                {busy === "scan" ? "扫描中…" : preview ? "重新扫描" : "扫描预览"}
              </button>
            </div>
          </div>
          {error && <div className="alert error" role="alert">{error}</div>}
          {(preview || notice) && <div className="scan-summary" role="status">
            <ScanSearch size={16} aria-hidden="true" />
            <div>
              {notice && <p className="scan-import-notice">{notice}</p>}
              {scanSummary && <strong>{scanSummary}</strong>}
              {scanDetails && <p className="muted">{scanDetails}</p>}
            </div>
          </div>}
          {items.length > 0 && <div className="scan-preview">
            <div className="scan-preview-header">
              <label className="scan-select-all">
                <input type="checkbox" aria-label="全选导入文件" checked={selected.size === items.length}
                  ref={(checkbox) => { if (checkbox) checkbox.indeterminate = selected.size > 0 && selected.size < items.length; }}
                  disabled={!!busy} onChange={(event) => setSelected(new Set(event.target.checked ? items.map((item) => item.path) : []))} />
                <span>全选</span>
              </label>
              <span className="muted">已选 {selected.size} / {items.length} 个文件</span>
            </div>
            <div className="scan-preview-list">
              {items.map((item) => {
                const filename = item.path.split(/[\\/]/).at(-1) || item.name;
                return <label key={item.path} className="scan-preview-item">
                  <input type="checkbox" aria-label={`导入：${filename}`} checked={selected.has(item.path)}
                    disabled={!!busy} onChange={(event) => selectFile(item.path, event.target.checked)} />
                  <span className="scan-file-copy">
                    <strong title={filename}>{filename}</strong>
                    <small className="muted" title={item.path}>{item.path}</small>
                  </span>
                  <span className="scan-file-meta muted">{item.db_type || "其他"}{item.category && ` / ${item.category}`}</span>
                </label>;
              })}
            </div>
          </div>}
          <details className="context-details scan-import-rules"><summary>支持格式与识别规则</summary>
            <p>{module === "articles" ? "支持 Markdown、PDF、Word、Excel、PowerPoint、TXT 和 HTML 文档。" : module === "scripts" ? "支持 SQL、Shell、Python、PowerShell、BAT 和 CMD 脚本。" : "支持 EXE、MSI、BIN、ZIP、7Z、RAR、ISO、TAR、GZ、RPM、DEB、DMG 和 APK 文件。"}</p>
            <p>{module === "articles" ? "根据目录识别数据库与分类。" : "根据文件与目录生成导入记录。"}重复记录会跳过，已有内容保持不变。</p>
            <p>只在点击“导入所选”后写入，源文件保持不变。</p>
          </details>
        </div>
        {items.length > 0 && <footer className="modal-actions scan-import-footer">
          <button type="button" className="button primary" disabled={!!busy || !selected.size} onClick={() => void run("import")}>
            {busy === "import" ? "导入中…" : `导入所选（${selected.size}）`}
          </button>
        </footer>}
      </section>
    </div>}
  </>;
}
