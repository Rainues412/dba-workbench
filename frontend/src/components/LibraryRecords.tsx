import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Copy, FileText, FolderOpen, Maximize2, Minimize2, MoreHorizontal, Pencil, Pin, Trash2, X } from "lucide-react";
import screenfull from "screenfull";
import { api, Entity } from "../api/client";
import type { CrudConfig } from "./CrudPage";
import { DatabaseLabel } from "./DatabaseLabel";
import { EntityDetails } from "./EntityDetails";
import { LocalFileLinks } from "./LocalFileLinks";
import { EmptyState, ErrorState, LoadingState } from "./States";
import { FileName } from "./FileName";
import { SelectionIndicator, SelectionMotion } from "./SelectionMotion";
import { usePreference } from "../preferences";
import { ScriptCodePreview } from "./ScriptCodePreview";
import { useDesktopWindow } from "./DesktopWindowControls";
import { AppDialog } from "./AppDialog";
import { FavoriteButton } from "./FavoriteButton";

const MarkdownFilePreview = lazy(() => import("./MarkdownFilePreview").then((module) => ({ default: module.MarkdownFilePreview })));

function recordTitle(config: CrudConfig, row: Entity) {
  return String(row[config.titleField] || "未命名记录");
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

export function LibraryRecords({ config, rows, selectedId, disabled, searchQuery = "", onPreview, onEdit, onUpdate, onRemove, onNotice }: {
  config: CrudConfig;
  rows: Entity[];
  selectedId: number | null;
  disabled: boolean;
  searchQuery?: string;
  onPreview: (id: number) => void;
  onEdit: (id: number) => void;
  onUpdate: (row: Entity, payload: Record<string, unknown>) => Promise<void>;
  onRemove: (row: Entity) => Promise<void>;
  onNotice: (message: string) => void;
}) {
  const Icon = config.icon;
  return <SelectionMotion><ul className="library-record-list" aria-label={`${config.title}记录`} onKeyDown={(event) => {
    if (config.key !== "scripts" || disabled || !(event.target instanceof HTMLButtonElement) || !event.target.matches(".library-record-title")) return;
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); event.target.click(); return; }
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    const titles = [...event.currentTarget.querySelectorAll<HTMLButtonElement>(".library-record-title:not(:disabled)")];
    const index = titles.indexOf(event.target);
    event.preventDefault();
    titles[index + (event.key === "ArrowDown" ? 1 : -1)]?.focus();
  }}>
    {rows.map((row) => {
      const title = recordTitle(config, row);
      const filePath = config.key !== "resources" && config.fileLinks ? String(row[config.fileLinks.pathField] || "").trim() : "";
      const description = String(row.summary || row.description || (config.key === "resources" ? row.path || row.url : "") || "");
      return <li key={row.id} className={`library-record${config.key === "scripts" ? " script-record" : ""}${selectedId === row.id ? " selected" : ""}`}
        data-previewable={config.key !== "resources" && !disabled ? "" : undefined}
        onClick={(event) => {
          if (config.key === "resources" || disabled || event.defaultPrevented || !(event.target instanceof Element)) return;
          // Keep nested controls independent; the title already handles keyboard activation.
          if (event.target.closest("button, a, input, select, textarea, details, [role='button'], [contenteditable='true']")) return;
          const selection = window.getSelection();
          if (selection && !selection.isCollapsed && event.currentTarget.contains(selection.anchorNode)) return;
          event.currentTarget.querySelector<HTMLButtonElement>(".library-record-title")?.focus({ preventScroll: true });
          onPreview(row.id);
        }}>
        {selectedId === row.id && <SelectionIndicator className="record-active-indicator" radius={0} />}
        <span className={`library-record-icon ${config.key}`} aria-hidden="true"><Icon size={20} /></span>
        <div className="library-record-copy">
          <div className="library-record-heading">
            <div className="library-record-summary">
              {config.key === "resources" && config.fileLinks ? <div className="library-resource-links" title={title}><LocalFileLinks row={row} label={title} config={config.fileLinks} disabled={disabled} onNotice={onNotice} compact /></div> : <button type="button" className="library-record-title" title={title} aria-label={`预览：${title}`} aria-pressed={selectedId === row.id} disabled={disabled} onClick={() => onPreview(row.id)}><FileName text={title} path={filePath} query={searchQuery} /></button>}
              {filePath ? <p className="library-record-path" title={filePath}><FolderOpen size={13} aria-hidden="true" /><span><FileName text={filePath} path={filePath} /></span></p>
                : description && <p className="library-record-description" title={description}>{description}</p>}
            </div>
            <div className="library-record-actions">
              <FavoriteButton active={Boolean(row.is_favorite)} disabled={disabled} onToggle={() => onUpdate(row, { is_favorite: row.is_favorite ? 0 : 1 })} />
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
  </ul></SelectionMotion>;
}

export function LibraryPreview({ config, id, open = true, editorOpen, onClose, onEdit, onRefresh }: {
  config: CrudConfig;
  id: number | null;
  open?: boolean;
  editorOpen: boolean;
  onClose: () => void;
  onEdit: (id: number) => void;
  onRefresh: () => Promise<void>;
}) {
  const headingId = useId();
  const desktop = Boolean(useDesktopWindow());
  const client = useQueryClient();
  const navigate = useNavigate();
  const lastView = useRef<number | null>(null);
  const showDocumentInfo = usePreference("showDocumentInfo") === "true" && config.key === "scripts";
  const readerRef = useRef<HTMLDivElement>(null);
  const fullscreenTrigger = useRef<HTMLButtonElement>(null);
  const savedPageScroll = useRef(0);
  const [expanded, setExpanded] = useState(false);
  const expandedRef = useRef(expanded);
  expandedRef.current = expanded;
  const [feedback, setFeedback] = useState({ text: "" });
  const message = feedback.text;
  const setMessage = useCallback((text: string) => setFeedback({ text }), []);
  useEffect(() => {
    if (!/^(已|正文已|路径已)/.test(feedback.text)) return;
    const timer = window.setTimeout(() => setFeedback({ text: "" }), 3000);
    return () => window.clearTimeout(timer);
  }, [feedback]);
  const [drawer, setDrawer] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1399px)").matches);
  const detail = useQuery({
    queryKey: [config.key, "detail", id],
    queryFn: ({ signal }) => api<Entity>(`${config.path}${id}`, { signal }),
    enabled: id !== null,
  });
  const row = detail.data;
  const recentViews = useQuery({
    queryKey: ["scripts", "recent-views"],
    queryFn: () => api<{ id: number; title: string; viewed_at: string }[]>("/api/scripts/recent-views"),
    enabled: Boolean(open && row && showDocumentInfo && !drawer),
  });
  const savedContent = String(row?.content || "");
  const linkedPath = String(row?.file_path || "");
  const hasLinkedFile = Boolean(row && linkedPath.trim());
  const summary = String(row?.summary || row?.description || "").trim();
  const showSummary = config.key !== "articles" && summary && !(hasLinkedFile && /^来自\s/.test(summary));
  const visual = useQuery({
    queryKey: [config.key, "visual-preview", id, linkedPath],
    queryFn: ({ signal }) => api<{ filename: string; viewer: string; viewer_version?: string; viewer_url: string; asset_url?: string }>(`${config.path}${id}/visual-preview`, { signal }),
    enabled: id !== null && hasLinkedFile,
    retry: false,
    gcTime: 0,
  });
  const needsFile = Boolean(config.key === "scripts" && row && !savedContent.trim() && linkedPath.trim() && visual.isError);
  const file = useQuery({
    queryKey: [config.key, "file-preview", id, linkedPath],
    queryFn: ({ signal }) => api<{ filename: string; content: string; truncated: boolean }>(`${config.path}${id}/file-preview`, { signal }),
    enabled: id !== null && needsFile,
    retry: false,
    gcTime: 0,
  });
  const body = needsFile ? file.data?.content || "" : savedContent;
  useEffect(() => {
    if (!open || id === null) { lastView.current = null; return; }
    if (config.key !== "scripts" || row?.id !== id || lastView.current === id) return;
    lastView.current = id;
    void api(`/api/scripts/${id}/view`, { method: "POST" }).then(() => {
      void client.invalidateQueries({ queryKey: ["scripts", "recent-views"] });
      void client.invalidateQueries({ predicate: ({ queryKey }) => queryKey[0] === "scripts" && typeof queryKey[1] === "number", refetchType: "none" });
    }).catch(() => undefined);
  }, [client, config.key, id, open, row?.id]);
  useEffect(() => {
    setMessage("");
  }, [id]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1399px)");
    const changed = () => { if (!document.fullscreenElement && !expandedRef.current) setDrawer(media.matches); };
    media.addEventListener("change", changed);
    document.addEventListener("fullscreenchange", changed);
    return () => { media.removeEventListener("change", changed); document.removeEventListener("fullscreenchange", changed); };
  }, []);
  useEffect(() => {
    if (!screenfull.isEnabled) return;
    const changed = () => {
      const active = screenfull.element === readerRef.current;
      setExpanded(active);
      if (!active) requestAnimationFrame(() => { window.scrollTo(0, savedPageScroll.current); fullscreenTrigger.current?.focus({ preventScroll: true }); });
    };
    screenfull.on("change", changed);
    return () => screenfull.off("change", changed);
  }, []);
  useEffect(() => {
    if (!expanded || desktop) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && screenfull.isEnabled) {
        event.preventDefault(); event.stopPropagation(); void screenfull.exit();
      }
    };
    document.addEventListener("keydown", escape, true);
    return () => document.removeEventListener("keydown", escape, true);
  }, [expanded, desktop]);

  const title = row ? recordTitle(config, row) : "记录预览";
  async function closePreview() {
    if (screenfull.isEnabled && screenfull.element === readerRef.current) await screenfull.exit();
    const trigger = document.querySelector<HTMLButtonElement>('.library-record-title[aria-pressed="true"]') ?? document.querySelector<HTMLButtonElement>(".preview-toggle");
    setExpanded(false);
    onClose();
    trigger?.focus({ preventScroll: true });
  }
  async function toggleReading() {
    if (desktop) {
      setExpanded((value) => !value);
      if (expanded) setDrawer(window.matchMedia("(max-width: 1399px)").matches);
      return;
    }
    if (!screenfull.isEnabled || !readerRef.current) return;
    try {
      if (!expanded) savedPageScroll.current = window.scrollY;
      await screenfull.toggle(readerRef.current);
    } catch { setMessage("暂时无法进入大屏阅读，请重试或使用浏览器的全屏功能。"); }
  }
  async function editRecord() {
    if (screenfull.isEnabled && screenfull.element === readerRef.current) await screenfull.exit();
    onEdit(id!);
  }
  function notify(value: string) { setMessage(value); }
  async function copyContent() {
    try { await navigator.clipboard.writeText(body); notify(file.data?.truncated && needsFile ? "已复制当前预览片段" : "正文已复制"); }
    catch { notify("复制失败，请手动选择正文复制"); }
  }
  function dismissPreview() {
    if (expanded && desktop) {
      setExpanded(false);
      setDrawer(window.matchMedia("(max-width: 1399px)").matches);
      fullscreenTrigger.current?.focus({ preventScroll: true });
    } else void closePreview();
  }
  const canExpand = desktop || screenfull.isEnabled;
  const content = <div ref={readerRef} className={`library-reader${expanded ? " expanded" : ""}${expanded && desktop ? " desktop-expanded" : ""}`}
    onKeyDown={(event) => {
      if (event.key !== "Escape" || !desktop || !expanded || event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      dismissPreview();
    }}>
    <header className="library-preview-heading"><h2 id={headingId} title={title}><FileName text={title} path={linkedPath} /></h2><div>
      <button ref={fullscreenTrigger} type="button" className="icon-button" aria-label={expanded ? "退出大屏阅读" : "大屏阅读"} title={canExpand ? expanded ? "退出大屏阅读（Esc）" : "大屏阅读" : "当前浏览器不支持全屏阅读"} disabled={!row || !canExpand} onClick={() => void toggleReading()}>{expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>
      <button type="button" className="button small" disabled={!row || detail.isLoading || !!detail.error} onClick={() => void editRecord()}><Pencil size={14} />编辑</button>
      <button type="button" className="icon-button" aria-label="关闭预览" title="关闭预览" onClick={closePreview}><X size={19} /></button>
    </div></header>
    {row && !detail.isLoading && !detail.error && <div className="library-preview-tools">
      <div className="library-preview-overview">
        <RecordMeta config={config} row={row} />
        {Boolean(row.updated_at) && <dl className="library-preview-meta"><dt>更新于</dt><dd title={String(row.updated_at)}>{String(row.updated_at).replace("T", " ").slice(0, 16)}</dd></dl>}
      </div>
      {config.fileLinks && <section className="library-preview-actions" aria-label="快捷访问">
        <LocalFileLinks row={row} label={title} config={config.fileLinks} disabled={false} onNotice={notify} actionLabel={config.fileLinks.openLabel} compact />
      </section>}
    </div>}
    <div className={`library-preview-body${showDocumentInfo && row ? " has-script-inspector" : ""}`}>
      <div className="library-preview-main">
      {message && <p className="library-inline-notice" aria-live="polite">{message}</p>}
      {id === null ? <EmptyState title="选择一条记录预览" description="" />
        : detail.isLoading ? <LoadingState label="正在读取完整记录" />
        : detail.error || !row ? <ErrorState message="预览加载失败，请重试" retry={() => void detail.refetch()} />
        : <>
          <>
              {showSummary && <p className="library-preview-summary">{summary}</p>}
              {hasLinkedFile && <section className="library-preview-section library-visual-preview" aria-label="原文件预览" title={visual.data?.filename}>
                {visual.isLoading ? <LoadingState label="正在准备原文件预览" />
                  : visual.error ? <ErrorState message={`原文件预览失败：${visual.error.message}`} retry={() => void visual.refetch()} />
                  : visual.data?.viewer === "markdown" ? <Suspense fallback={<LoadingState label="正在加载 Markdown 查看器" />}><MarkdownFilePreview filename={visual.data.filename} sourceUrl={visual.data.viewer_url} assetUrl={visual.data.asset_url!} expanded={expanded} /></Suspense>
                  : visual.data ? <iframe className="library-visual-frame" title={`原文件预览：${visual.data.filename}`} src={visual.data.viewer_url} sandbox="allow-downloads allow-forms allow-popups allow-same-origin allow-scripts" referrerPolicy="no-referrer" />
                  : null}
              </section>}
              {config.key === "articles" && !hasLinkedFile && <EmptyState title="尚未关联源文件" description="请编辑记录，填写源文件路径后预览。" />}
              {config.key === "scripts" && (savedContent || needsFile || !hasLinkedFile) && <section className="library-preview-section" aria-label="正文预览"><div className="library-content-heading"><h3>脚本正文</h3>
                <button type="button" className="button small" disabled={!body || (needsFile && (file.isFetching || !!file.error))} onClick={() => void copyContent()}><Copy size={14} />{needsFile && file.data?.truncated ? "复制预览" : "复制正文"}</button>
              </div>
                {needsFile && <p className="library-file-source muted"><span title={linkedPath}><FolderOpen size={13} aria-hidden="true" /><FileName text={file.data?.filename || linkedPath} path={linkedPath} /></span>
                  <button type="button" className="button small" disabled={file.isFetching} onClick={() => void file.refetch()}>重新读取</button>
                </p>}
                {needsFile && file.isLoading ? <LoadingState label="正在读取关联文件" />
                  : needsFile && file.error ? <ErrorState message={`关联文件预览失败：${file.error.message}`} retry={() => void file.refetch()} />
                  : <>
                    {needsFile && file.data?.truncated && <p className="library-inline-notice" role="status">文件较大，仅显示前 512 KB 预览；请快捷打开查看完整内容。</p>}
                    {body ? <ScriptCodePreview key={row.id} text={body} />
                      : <p className="muted">{needsFile ? "关联文件为空。" : "尚未填写正文，也未关联本地文件。"}</p>}
                  </>}
              </section>}
              {config.key === "scripts" && <details className="library-history"><summary><FileText size={15} />历史版本</summary><EntityDetails module={config.key} item={row} onRefresh={onRefresh} readOnly /></details>}
          </>
        </>}
      </div>
      {showDocumentInfo && row && <aside className="script-inspector" aria-label="文档信息">
        <h3>文档信息</h3>
        <dl><dt>版本</dt><dd>{String(row.version || "—")}</dd><dt>数据库</dt><dd>{String(row.db_type || "—")}</dd>
          <dt>更新于</dt><dd>{String(row.updated_at || "—").replace("T", " ").slice(0, 16)}</dd></dl>
        <h3>最近查看</h3>
        {recentViews.isError ? <p className="muted">暂时无法读取最近查看。</p> : recentViews.data?.length
          ? <ul>{recentViews.data.map((record) => <li key={record.id}><button type="button" title={record.title}
            disabled={record.id === id} onClick={() => navigate(`/scripts?preview=${record.id}`, { state: { previewSearch: true } })}>{record.title}</button></li>)}</ul>
          : <p className="muted">{recentViews.isLoading ? "正在读取…" : "暂无查看记录。"}</p>}
      </aside>}
    </div>
  </div>;
  // LibraryLayout retains the viewer until its exit transition finishes.
  if (drawer && (id === null || editorOpen)) return null;
  return drawer ? <AppDialog className={`library-preview library-preview-drawer${!open ? " is-closing" : ""}${expanded && desktop ? " desktop-expanded-drawer" : ""}`} labelledBy={headingId} onClose={dismissPreview} dimBackground={false} inert={!open}>{content}</AppDialog>
    : <aside className="panel library-preview" aria-label="记录预览" onKeyDown={(event) => { if (event.key === "Escape" && !expanded) void closePreview(); }}>{content}</aside>;
}
