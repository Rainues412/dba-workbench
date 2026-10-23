import { lazy, Suspense, useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy, FileText, FolderOpen, MoreHorizontal, Pencil, Pin, Star, Trash2, X } from "lucide-react";
import { api, Entity } from "../api/client";
import type { CrudConfig } from "./CrudPage";
import { DatabaseLabel } from "./DatabaseLabel";
import { EntityDetails } from "./EntityDetails";
import { LocalFileLinks } from "./LocalFileLinks";
import { EmptyState, ErrorState, LoadingState } from "./States";

const MarkdownFilePreview = lazy(() => import("./MarkdownFilePreview").then((module) => ({ default: module.MarkdownFilePreview })));

function recordTitle(config: CrudConfig, row: Entity) {
  return String(row[config.columns[0].name] || "未命名记录");
}

function RecordMeta({ config, row }: { config: CrudConfig; row: Entity }) {
  const database = String(row[config.classification?.databaseField || (config.key === "scripts" ? "db_type" : "wb_db")] || "");
  const category = String(row[config.classification?.categoryField || "category"] || "");
  const context = new Set([database, category, row.version ? `v${row.version}` : ""].map((value) => value.toLowerCase()));
  const tags = [...new Set(String(row.tags || "").split(/[,，]/).map((tag) => tag.trim()).filter(Boolean))].filter((tag) => !context.has(tag.toLowerCase()));
  if (!database && !category && !row.version && !tags.length) return null;
  return <div className="library-record-meta">
    {database && <DatabaseLabel name={database} />}
    {category && <span className="badge" title={category}>{category}</span>}
    {Boolean(row.version) && <span className="badge" title={`v${row.version}`}>v{String(row.version)}</span>}
    {tags.slice(0, 3).map((tag, index) => <span className="library-tag" key={`${tag}-${index}`} title={tag}>{tag}</span>)}
    {tags.length > 3 && <span className="library-tag" title={tags.join("、")}>+{tags.length - 3}</span>}
  </div>;
}

export function LibraryRecords({ config, rows, selectedId, disabled, onPreview, onEdit, onUpdate, onRemove, onNotice }: {
  config: CrudConfig;
  rows: Entity[];
  selectedId: number | null;
  disabled: boolean;
  onPreview: (id: number) => void;
  onEdit: (id: number) => void;
  onUpdate: (row: Entity, payload: Record<string, unknown>) => Promise<void>;
  onRemove: (row: Entity) => Promise<void>;
  onNotice: (message: string) => void;
}) {
  const Icon = config.icon;
  return <ul className="library-record-list" aria-label={`${config.title}记录`}>
    {rows.map((row) => {
      const title = recordTitle(config, row);
      const filePath = config.key !== "resources" && config.fileLinks ? String(row[config.fileLinks.pathField] || "").trim() : "";
      const description = String(row.summary || row.description || (config.key === "resources" ? row.path || row.url : "") || "");
      return <li key={row.id} className={`library-record${selectedId === row.id ? " selected" : ""}`}>
        <span className={`library-record-icon ${config.key}`} aria-hidden="true"><Icon size={20} /></span>
        <div className="library-record-copy">
          <div className="library-record-heading">
            <div className="library-record-summary">
              {config.key === "resources" && config.fileLinks ? <div className="library-resource-links" title={title}><LocalFileLinks row={row} label={title} config={config.fileLinks} disabled={disabled} onNotice={onNotice} compact /></div> : <button type="button" className="library-record-title" title={title} aria-label={`预览：${title}`} aria-pressed={selectedId === row.id} disabled={disabled} onClick={() => onPreview(row.id)}>{title}</button>}
              {filePath ? <p className="library-record-path" title={filePath}><FolderOpen size={13} aria-hidden="true" /><span>{filePath}</span></p>
                : description && <p className="library-record-description" title={description}>{description}</p>}
            </div>
            <div className="library-record-actions">
              <button type="button" className={`icon-button${row.is_favorite ? " is-favorite" : ""}`} aria-label={row.is_favorite ? "取消收藏" : "收藏"} title={row.is_favorite ? "取消收藏" : "收藏"} disabled={disabled} onClick={() => void onUpdate(row, { is_favorite: row.is_favorite ? 0 : 1 })}><Star size={16} fill={row.is_favorite ? "currentColor" : "none"} /></button>
              {config.key === "articles" && <button type="button" className={`icon-button${row.is_pinned ? " is-pinned" : ""}`} aria-label={row.is_pinned ? "取消置顶" : "置顶"} title={row.is_pinned ? "取消置顶" : "置顶"} disabled={disabled} onClick={() => void onUpdate(row, { is_pinned: row.is_pinned ? 0 : 1 })}><Pin size={15} fill={row.is_pinned ? "currentColor" : "none"} /></button>}
              <button type="button" className="icon-button" aria-label="查看/编辑" title={`编辑：${title}`} disabled={disabled} onClick={() => onEdit(row.id)}><Pencil size={15} /></button>
              <details className="library-more"><summary aria-label={`更多操作：${title}`} title="更多操作"><MoreHorizontal size={17} /></summary><div>
                <button type="button" className="button small danger" disabled={disabled} onClick={() => void onRemove(row)}><Trash2 size={14} />删除记录</button>
              </div></details>
            </div>
          </div>
          <RecordMeta config={config} row={row} />
          <div className="library-record-footer">
            {config.fileLinks && config.key !== "resources" && <LocalFileLinks row={row} label={title} config={config.fileLinks} disabled={disabled} onNotice={onNotice} actionLabel={config.fileLinks.openLabel} compact />}
            {Boolean(row.updated_at) && <small className="library-updated" title={String(row.updated_at)}>更新于 {String(row.updated_at).replace("T", " ").slice(0, 16)}</small>}
          </div>
        </div>
      </li>;
    })}
  </ul>;
}

export function LibraryPreview({ config, id, onClose, onEdit, onNotice, onRefresh }: {
  config: CrudConfig;
  id: number | null;
  onClose: () => void;
  onEdit: (id: number) => void;
  onNotice: (message: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const headingId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [message, setMessage] = useState("");
  const [drawer, setDrawer] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1399px)").matches);
  const detail = useQuery({
    queryKey: [config.key, "detail", id],
    queryFn: ({ signal }) => api<Entity>(`${config.path}${id}`, { signal }),
    enabled: id !== null,
  });
  const row = detail.data;
  const savedContent = String(row?.content || "");
  const linkedPath = String(row?.file_path || "");
  const hasLinkedFile = Boolean(row && linkedPath.trim());
  const summary = String(row?.summary || row?.description || "").trim();
  const showSummary = summary && !(hasLinkedFile && /^来自\s/.test(summary));
  const visual = useQuery({
    queryKey: [config.key, "visual-preview", id, linkedPath, row?.updated_at],
    queryFn: ({ signal }) => api<{ filename: string; viewer: string; viewer_version?: string; viewer_url: string; asset_url?: string }>(`${config.path}${id}/visual-preview`, { signal }),
    enabled: id !== null && hasLinkedFile,
    retry: false,
    gcTime: 0,
  });
  const needsFile = Boolean(config.key === "scripts" && row && !savedContent.trim() && linkedPath.trim() && visual.isError);
  const file = useQuery({
    queryKey: [config.key, "file-preview", id, linkedPath, row?.updated_at],
    queryFn: ({ signal }) => api<{ filename: string; content: string; truncated: boolean }>(`${config.path}${id}/file-preview`, { signal }),
    enabled: id !== null && needsFile,
    retry: false,
    gcTime: 0,
  });
  const body = needsFile ? file.data?.content || "" : savedContent;
  useEffect(() => {
    setMessage("");
  }, [id]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1399px)");
    const changed = () => setDrawer(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!drawer || id === null || !dialog) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); document.body.style.overflow = previousOverflow; };
  }, [drawer, id]);

  const title = row ? recordTitle(config, row) : "记录预览";
  function closePreview() {
    const trigger = document.querySelector<HTMLButtonElement>('.library-record-title[aria-pressed="true"]');
    if (dialogRef.current?.open) dialogRef.current.close();
    onClose();
    trigger?.focus();
  }
  function notify(value: string) { setMessage(value); onNotice(value); }
  async function copyContent() {
    try { await navigator.clipboard.writeText(body); notify(file.data?.truncated && needsFile ? "已复制当前预览片段" : "正文已复制"); }
    catch { notify("复制失败，请手动选择正文复制"); }
  }
  const content = <>
    <header className="library-preview-heading"><h2 id={headingId} title={title}>{title}</h2><div>
      <button type="button" className="button small" disabled={!row || detail.isLoading || !!detail.error} onClick={() => onEdit(id!)}><Pencil size={14} />编辑</button>
      <button type="button" className="icon-button" aria-label="关闭预览" title="关闭预览" onClick={closePreview}><X size={19} /></button>
    </div></header>
    <div className="library-preview-body">
      {message && <p className="library-inline-notice" aria-live="polite">{message}</p>}
      {id === null ? <EmptyState title="选择一条记录预览" description="点击列表标题即可查看，文件和网址通过独立按钮打开。" />
        : detail.isLoading ? <LoadingState label="正在读取完整记录" />
        : detail.error || !row ? <ErrorState message="预览加载失败，请重试" retry={() => void detail.refetch()} />
        : <>
          <div className="library-preview-overview">
            <RecordMeta config={config} row={row} />
            {Boolean(row.updated_at) && <dl className="library-preview-meta"><dt>更新于</dt><dd title={String(row.updated_at)}>{String(row.updated_at).replace("T", " ").slice(0, 16)}</dd></dl>}
          </div>
          {config.fileLinks && <section className="library-preview-section library-preview-actions" aria-label="快捷访问">
            <LocalFileLinks row={row} label={title} config={config.fileLinks} disabled={false} onNotice={notify} actionLabel={config.fileLinks.openLabel} compact />
            {!row[config.fileLinks.pathField] && !(config.fileLinks.urlField && row[config.fileLinks.urlField]) && <p className="muted">未关联本地文件或网址</p>}
          </section>}
          <>
              {showSummary && <p className="library-preview-summary">{summary}</p>}
              {hasLinkedFile && <section className="library-preview-section library-visual-preview" aria-label="原文件预览">
                <div className="library-content-heading"><h3>原文件预览</h3>
                  <span className="muted" title={visual.data?.filename}>{visual.data?.filename || "内置查看器"}</span>
                </div>
                {visual.isLoading ? <LoadingState label="正在准备原文件预览" />
                  : visual.error ? <ErrorState message={`原文件预览失败：${visual.error.message}`} retry={() => void visual.refetch()} />
                  : visual.data?.viewer === "markdown" ? <Suspense fallback={<LoadingState label="正在加载 Markdown 查看器" />}><MarkdownFilePreview filename={visual.data.filename} sourceUrl={visual.data.viewer_url} assetUrl={visual.data.asset_url!} /></Suspense>
                  : visual.data ? <iframe className="library-visual-frame" title={`原文件预览：${visual.data.filename}`} src={visual.data.viewer_url} sandbox="allow-downloads allow-forms allow-popups allow-same-origin allow-scripts" referrerPolicy="no-referrer" />
                  : null}
              </section>}
              {config.key === "articles" && !hasLinkedFile && <EmptyState title="尚未关联源文件" description="请编辑记录，填写源文件路径后预览。" />}
              {config.key === "scripts" && (savedContent || needsFile || !hasLinkedFile) && <section className="library-preview-section" aria-label="正文预览"><div className="library-content-heading"><h3>脚本正文（只读）</h3>
                <button type="button" className="button small" disabled={!body || (needsFile && (file.isFetching || !!file.error))} onClick={() => void copyContent()}><Copy size={14} />{needsFile && file.data?.truncated ? "复制预览" : "复制正文"}</button>
              </div>
                {needsFile && <p className="library-file-source muted">预览来源：关联文件{file.data ? ` · ${file.data.filename}` : ""}
                  <button type="button" className="button small" disabled={file.isFetching} onClick={() => void file.refetch()}>重新读取</button>
                </p>}
                {needsFile && file.isLoading ? <LoadingState label="正在读取关联文件" />
                  : needsFile && file.error ? <ErrorState message={`关联文件预览失败：${file.error.message}`} retry={() => void file.refetch()} />
                  : <>
                    {needsFile && file.data?.truncated && <p className="library-inline-notice" role="status">文件较大，仅显示前 512 KB 预览；请快捷打开查看完整内容。</p>}
                    {body ? <pre className="library-code"><code>{body}</code></pre>
                      : <p className="muted">{needsFile ? "关联文件为空。" : "尚未填写正文，也未关联本地文件。"}</p>}
                  </>}
              </section>}
              {config.key === "scripts" && <details className="library-history"><summary><FileText size={15} />历史版本</summary><EntityDetails module={config.key} item={row} onRefresh={onRefresh} readOnly /></details>}
          </>
        </>}
    </div>
  </>;
  if (drawer && id === null) return null;
  return drawer ? <dialog ref={dialogRef} className="library-preview library-preview-drawer" aria-labelledby={headingId} onCancel={(event) => { event.preventDefault(); closePreview(); }} onClick={(event) => { if (event.target === event.currentTarget) closePreview(); }}>{content}</dialog>
    : <aside className="panel library-preview" aria-label="记录预览" onKeyDown={(event) => { if (event.key === "Escape") closePreview(); }}>{content}</aside>;
}
