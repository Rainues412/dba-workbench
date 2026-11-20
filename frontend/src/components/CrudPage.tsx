import { FormEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Archive, ArrowLeft, CalendarDays, CheckCircle2, ChevronDown, ChevronsUp, FolderOpen, Minus, PanelRight, Pencil, Pin, Plus, RotateCcw, Search, Star, Trash2, Undo2, X } from "lucide-react";
import { useLocation, useSearchParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { api, ApiError, Entity, entityApi } from "../api/client";
import { usePreference } from "../preferences";
import { CategoryNavigation } from "./CategoryNavigation";
import { DatabaseLabel } from "./DatabaseLabel";
import type { Classification, Facets } from "./CategoryNavigation";
import { Pagination } from "./Pagination";
import { LocalFileLinks } from "./LocalFileLinks";
import { LibraryPreview, LibraryRecords } from "./LibraryRecords";
import { LibraryLayout } from "./LibraryLayout";
import type { FileLinksConfig } from "./LocalFileLinks";
import { ScanImport } from "./ScanImport";
import { EntityDetails } from "./EntityDetails";
import { CustomerDirectory, CustomerFields, CustomerProjectDrawer, CustomerProjectEditor, projectInCustomerList, customerProfilePayload, makeCustomerDraft, type ProjectSelection } from "./CustomerProjects";
import { DateField } from "./DateField";
import { EmptyState, ErrorState, LoadingState, TableSkeleton } from "./States";

type Field = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "date" | "url" | "number" | "select";
  required?: boolean;
  options?: string[];
  defaultValue?: string | number;
};

export type CrudConfig = {
  key: string;
  title: string;
  description: string;
  path: string;
  icon: LucideIcon;
  fields: Field[];
  columns: { name: string; label: string }[];
  classification?: Classification;
  fileLinks?: FileLinksConfig;
};

type LibraryPreviewState = { id: number | null; open: boolean };

export function CrudPage({ config }: { config: CrudConfig }) {
  return <CrudContent key={config.key} config={config} />;
}

function CrudContent({ config }: { config: CrudConfig }) {
  const PageIcon = config.icon;
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const handledPreview = useRef<number | null>(null);
  const currentPreview = useRef<LibraryPreviewState>({ id: null, open: false });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [keyword, setKeyword] = useState("");
  const [debouncedKeyword, setDebouncedKeyword] = useState("");
  const database = config.classification ? searchParams.get("database") ?? "" : "";
  const category = config.classification?.categoryField ? searchParams.get("category") ?? "" : "";
  const [status, setStatus] = useState("");
  const [taskArchive, setTaskArchive] = useState(false);
  const [priority, setPriority] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [locateId, setLocateId] = useState<number | null>(null);
  const [revealId, setRevealId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [projectEdit, setProjectEdit] = useState<ProjectSelection | null>(null);
  const [creating, setCreating] = useState(false);
  const [notification, setNotification] = useState({ message: "", error: false });
  const notice = notification.message;
  const setNotice = useCallback((message: string, error = false) => setNotification({ message, error }), []);
  useEffect(() => {
    if (!notification.message || notification.error) return;
    const timer = window.setTimeout(() => setNotification({ message: "", error: false }), 3000);
    return () => window.clearTimeout(timer);
  }, [notification]);
  const [projectJump, setProjectJump] = useState<{ key: string; mode: "list" | "drawer" } | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const paginationTop = useRef<number | null>(null);
  const filters: Record<string, string> = {};
  const isTask = config.key === "tasks";
  const isCustomer = config.key === "customers";
  const hasFavorites = ["scripts", "articles", "resources"].includes(config.key);
  const hasPreview = ["scripts", "articles"].includes(config.key);
  const requestedPreview = Number(searchParams.get("preview"));
  const previewTarget = hasPreview && Number.isSafeInteger(requestedPreview) && requestedPreview > 0 ? requestedPreview : null;
  const libraryPreview: LibraryPreviewState | undefined = hasPreview ? location.state?.libraryPreview : undefined;
  const previewId = previewTarget ?? libraryPreview?.id ?? null;
  const previewEnabled = previewTarget !== null || libraryPreview?.open === true;
  const previewSearch = location.state?.previewSearch === true;
  useLayoutEffect(() => { currentPreview.current = { id: previewId, open: previewEnabled }; }, [location.key, previewId, previewEnabled]);
  const recordTarget = searchParams.get("record");
  const createTarget = searchParams.get("create");
  const projectCustomer = Number(searchParams.get("customer"));
  const projectTarget = isCustomer && Number.isSafeInteger(projectCustomer) && projectCustomer > 0 ? searchParams.get("project") : null;
  const jumpMode = projectTarget && projectJump?.key === location.key ? projectJump.mode : null;
  const clearProjectTarget = useCallback(() => {
    if (!projectTarget) return;
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("customer");
      next.delete("project");
      return next;
    }, { replace: true });
  }, [projectTarget, setSearchParams]);
  const searchLabel = isCustomer ? "搜索客户名或项目名" : `按标题搜索${config.title}`;
  const autoPinScripts = usePreference("autoPinScripts") === "true";
  if (hasPreview && locateId !== null) filters.locate_id = String(locateId);
  if (isTask && taskArchive) filters.archived = "1";
  else if (isTask && status) filters.status = status;
  if (isTask && priority) filters.priority = priority;
  if (isTask && overdueOnly) filters.overdue = "1";
  if (hasFavorites && favoriteOnly) filters.favorite_only = "1";
  if (config.key === "scripts" && autoPinScripts && !debouncedKeyword) filters.auto_pin = "1";
  if (config.classification) {
    if (database) filters[config.classification.databaseField] = database;
    if (category && config.classification.categoryField) filters[config.classification.categoryField] = category;
  }
  const facets = useQuery({
    queryKey: [config.key, "facets"],
    queryFn: () => api<Facets>(`${config.path}facets`),
    enabled: !!config.classification,
  });
  const list = useQuery({
    queryKey: [config.key, page, pageSize, debouncedKeyword, filters],
    queryFn: ({ signal }) => entityApi.list<Entity>(config.path, page, debouncedKeyword, filters, pageSize, signal),
    placeholderData: (previousData, previousQuery) => {
      const previousFilters = previousQuery?.queryKey[4] as Record<string, string> | undefined;
      if (isCustomer && previousQuery?.queryKey[3] !== debouncedKeyword) return undefined;
      return isTask && Boolean(previousFilters?.archived) !== taskArchive ? undefined : keepPreviousData(previousData);
    },
    refetchInterval: isTask ? 60_000 : false,
  });
  const projectLocation = useQuery({
    queryKey: ["customers", "locate-project", location.key, projectCustomer, projectTarget, debouncedKeyword, pageSize],
    queryFn: ({ signal }) => entityApi.list<Entity>(config.path, 1, debouncedKeyword, { locate_id: String(projectCustomer) }, pageSize, signal),
    enabled: !!projectTarget && !jumpMode && keyword.trim() === debouncedKeyword,
  });
  useEffect(() => {
    const value = keyword.trim();
    if (!value) { setDebouncedKeyword(""); return; }
    const timer = window.setTimeout(() => setDebouncedKeyword(value), 180);
    return () => window.clearTimeout(timer);
  }, [keyword]);
  const detail = useQuery({
    queryKey: [config.key, "detail", selectedId],
    queryFn: () => entityApi.detail<Entity>(config.path, selectedId!),
    enabled: selectedId !== null,
  });
  useEffect(() => {
    const record = Number(recordTarget);
    if (Number.isSafeInteger(record) && record > 0) { setCreating(false); setProjectEdit(null); setSelectedId(record); }
  }, [recordTarget]);
  useEffect(() => {
    if (createTarget !== "1" || (config.key !== "scripts" && config.key !== "articles")) return;
    setSelectedId(null); setCreating(true);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("create");
      return next;
    }, { replace: true });
  }, [createTarget, config.key, setSearchParams]);
  useEffect(() => {
    if (projectTarget) { setCreating(false); setSelectedId(null); setProjectEdit(null); }
  }, [projectTarget, location.key]);
  useEffect(() => {
    if (!projectTarget || jumpMode || keyword.trim() !== debouncedKeyword || projectLocation.isFetching) return;
    if (!projectLocation.data && !projectLocation.isError) return;
    const target = projectLocation.data?.items.find((item) => item.id === projectCustomer);
    if (target && projectLocation.data && projectInCustomerList(target, projectTarget)) {
      paginationTop.current = null;
      client.setQueryData(["customers", projectLocation.data.page, pageSize, debouncedKeyword, {}], projectLocation.data);
      setPage(projectLocation.data.page);
      setProjectJump({ key: location.key, mode: "list" });
    } else {
      setProjectJump({ key: location.key, mode: "drawer" });
    }
  }, [client, pageSize, projectTarget, jumpMode, keyword, debouncedKeyword, projectLocation.data, projectLocation.isError, projectLocation.isFetching, projectCustomer, location.key]);
  useEffect(() => {
    if (jumpMode !== "list") return;
    function dismissOnClick(event: MouseEvent) {
      if (event.detail > 0) clearProjectTarget();
    }
    window.addEventListener("click", dismissOnClick, true);
    return () => window.removeEventListener("click", dismissOnClick, true);
  }, [jumpMode, clearProjectTarget]);
  useEffect(() => {
    if (list.data && !list.isPlaceholderData && page > Math.max(1, list.data.pages)) setPage(Math.max(1, list.data.pages));
  }, [list.data, list.isPlaceholderData, page]);
  useEffect(() => {
    if (previewTarget === null) { handledPreview.current = null; return; }
    if (handledPreview.current === previewTarget && !previewSearch) return;
    handledPreview.current = previewTarget;
    // A new search also locates the exact row using the server's ordering.
    setCreating(false); setSelectedId(null);
    setLocateId(previewTarget); setRevealId(previewTarget); setPage(1); setKeyword(""); setDebouncedKeyword(""); setFavoriteOnly(false);
  }, [previewTarget, previewSearch, location.key]);
  useEffect(() => {
    if (locateId === null || list.isFetching || list.isPlaceholderData || !list.data) return;
    setPage(list.data.page);
    setLocateId(null);
  }, [locateId, list.data, list.isFetching, list.isPlaceholderData]);
  useEffect(() => {
    if (revealId === null || revealId !== previewId || !previewEnabled || locateId !== null || list.isFetching || list.isPlaceholderData) return;
    const row = panelRef.current?.querySelector<HTMLElement>(".library-record.selected");
    if (!row) return;
    let active = true;
    const cancelReveal = () => { active = false; setRevealId(null); };
    const cancelOnKey = (event: KeyboardEvent) => {
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)) cancelReveal();
    };
    window.addEventListener("wheel", cancelReveal, { passive: true });
    window.addEventListener("touchmove", cancelReveal, { passive: true });
    window.addEventListener("pointerdown", cancelReveal);
    window.addEventListener("keydown", cancelOnKey);
    const frame = requestAnimationFrame(async () => {
      // Wait for the list/preview split to settle before revealing a lower row.
      const group = panelRef.current?.closest(".library-panels");
      const transitions = typeof group?.getAnimations === "function" ? group.getAnimations({ subtree: true }).filter((animation) => {
        const target = (animation.effect as KeyframeEffect | null)?.target;
        return target instanceof Element && target.matches("[data-panel], .library-preview-pane");
      }) : [];
      await Promise.all(transitions.map((animation) => animation.finished.catch(() => undefined)));
      if (!active || !row.isConnected) return;
      row.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
      setRevealId(null);
    });
    return () => {
      active = false; cancelAnimationFrame(frame);
      window.removeEventListener("wheel", cancelReveal);
      window.removeEventListener("touchmove", cancelReveal);
      window.removeEventListener("pointerdown", cancelReveal);
      window.removeEventListener("keydown", cancelOnKey);
    };
  }, [revealId, previewId, previewEnabled, locateId, list.data, list.isFetching, list.isPlaceholderData]);
  useLayoutEffect(() => {
    if (list.isPlaceholderData || paginationTop.current === null) return;
    if (list.error) { paginationTop.current = null; return; }
    if (!list.data || list.data.page !== page) return;
    const pagination = panelRef.current?.querySelector(".pagination");
    const previousTop = paginationTop.current;
    paginationTop.current = null;
    // Keep the clicked pager in place when the new page has a different height.
    if (pagination) window.scrollBy({ top: pagination.getBoundingClientRect().top - previousTop, behavior: "instant" });
  }, [list.data, list.error, list.isPlaceholderData, page]);

  function changePage(nextPage: number) {
    if (nextPage === page) return;
    clearProjectTarget();
    setLocateId(null);
    setRevealId(null);
    paginationTop.current = panelRef.current?.querySelector(".pagination")?.getBoundingClientRect().top ?? null;
    setPage(nextPage);
  }

  function changeClassification(nextDatabase: string, nextCategory: string) {
    setLocateId(null);
    setRevealId(null);
    paginationTop.current = null;
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (nextDatabase) next.set("database", nextDatabase); else next.delete("database");
      if (nextCategory) next.set("category", nextCategory); else next.delete("category");
      return next;
    }, { replace: true, state: { libraryPreview } });
    setPage(1);
  }

  const editorConfig = {
    ...config,
    fields: config.fields.map((field) => {
      const isClassification = field.name === config.classification?.databaseField || field.name === config.classification?.categoryField;
      return {
        ...field,
        defaultValue: filters[field.name] || field.defaultValue,
        options: isClassification
          ? [...new Set([...(field.options ?? []), ...(facets.data?.items ?? []).map((row) => String(row[field.name] ?? ""))].filter(Boolean))]
          : field.options,
      };
    }),
  };

  function changeTaskView() {
    paginationTop.current = null;
    setTaskArchive((value) => !value);
    setStatus(""); setPriority(""); setOverdueOnly(false);
    setKeyword(""); setDebouncedKeyword(""); setPage(1); setNotice("");
  }

  function closeEditor() {
    setSelectedId(null); setCreating(false);
    if (searchParams.has("record")) { const next = new URLSearchParams(searchParams); next.delete("record"); setSearchParams(next, { replace: true, state: { libraryPreview } }); }
  }
  function changeKeyword(value: string) {
    paginationTop.current = null;
    setKeyword(value);
    setPage(1);
    clearProjectTarget();
  }
  function changePreview(id: number | null, open: boolean) {
    currentPreview.current = { id, open };
    setLocateId(null);
    setRevealId(null);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("preview");
      return next;
    }, { replace: true, state: { libraryPreview: { id, open } } });
  }
  function togglePreview(id: number | null) {
    const current = currentPreview.current;
    changePreview(id, current.id !== id || !current.open);
  }
  function closePreview() { changePreview(previewId, false); }
  function editRecord(id: number) {
    if (previewTarget !== null) changePreview(previewId, previewEnabled);
    setCreating(false); setSelectedId(id);
  }
  async function refresh() {
    await Promise.all([client.invalidateQueries({
      queryKey: [config.key],
      // File previews issue new viewer URLs on each read. Keep the active file in place while refreshing record metadata.
      predicate: ({ queryKey: [, kind, id] }) => id !== previewId || (kind !== "visual-preview" && kind !== "file-preview"),
    }), client.invalidateQueries({ queryKey: ["dashboard"] })]);
  }

  async function save(payload: Record<string, unknown>, current?: Entity) {
    if (!creating && (!current || current.id !== selectedId)) throw new Error("详情未成功加载，不能保存，请重试读取记录");
    try {
      if (current) await entityApi.update(config.path, current.id, current.revision, payload);
      else await entityApi.create(config.path, payload);
      setNotice(current ? "记录已更新" : "记录已创建");
      closeEditor();
      await refresh();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409 && current && !isCustomer) {
        const overwrite = window.confirm("此记录已在其他窗口修改。确定重新读取最新版本并应用当前改动吗？");
        if (!overwrite) {
          closeEditor();
          await refresh();
          setNotice("已放弃本次修改并刷新最新数据");
          return;
        }
        const latest = await entityApi.detail<Entity>(config.path, current.id);
        await entityApi.update(config.path, latest.id, latest.revision, payload);
        closeEditor();
        await refresh();
        setNotice("已在最新版本上重新应用修改");
        return;
      }
      throw reason;
    }
  }

  async function remove(row: Entity) {
    if (!window.confirm(`确定删除“${String(row[config.columns[0].name] ?? "该记录")}”吗？`)) return;
    try {
      await entityApi.remove(config.path, row.id, row.revision);
      if (previewId === row.id) changePreview(null, false);
      setNotice("记录已删除");
      await refresh();
    } catch (reason) {
      setNotice(reason instanceof ApiError ? reason.message : "删除失败", true);
    }
  }

  async function quickUpdate(row: Entity, payload: Record<string, unknown>) {
    try {
      await entityApi.update(config.path, row.id, row.revision, payload);
      setNotice(Object.keys(payload).every((key) => key === "is_favorite" || key === "is_pinned") ? "" : "记录已更新");
      await refresh();
    }
    catch (reason) { setNotice(reason instanceof ApiError ? reason.message : "更新失败", true); if (reason instanceof ApiError && reason.status === 409) await refresh(); }
  }

  return <div className={`page${hasFavorites ? " library-page" : ""}`}>
    <header className="page-header"><div className="page-title-group"><span className="page-title-icon"><PageIcon size={24} /></span><div><p className="eyebrow">DATA MODULE</p><h1>{taskArchive ? "归档任务" : config.title}</h1></div></div><div className="button-row">
      {hasFavorites && <ScanImport key={config.key} module={config.key as "scripts" | "articles" | "resources"} onImported={refresh} />}
      {isTask && <div className="task-archive-entry">
        <button className="button" onClick={changeTaskView}>{taskArchive ? <ArrowLeft size={17} /> : <Archive size={17} />}{taskArchive ? "返回任务列表" : "查看归档"}</button>
        <details className="task-archive-rules" onKeyDown={(event) => {
          if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); }
        }}>
          <summary aria-label="归档规则" title="归档规则"><ChevronDown size={16} aria-hidden="true" /></summary>
          <div><p>已完成任务保留 15 天后自动归档，可在归档列表查看或恢复。</p><p>已完成及归档任务均按创建时间从新到旧排列。</p></div>
        </details>
      </div>}
      {!taskArchive && <button className="button primary" onClick={() => { setSelectedId(null); setCreating(true); }}><Plus size={17} />{isCustomer ? "新增客户" : "新增"}</button>}
    </div></header>
    <LibraryLayout module={config.key} enabled={hasFavorites}
      categories={config.classification ? (collapsed, onToggle) => <CategoryNavigation classification={config.classification!} data={facets.data} loading={facets.isLoading} error={!!facets.error} retry={() => void facets.refetch()} database={database} category={category} categoryOptions={config.fields.find((field) => field.name === config.classification?.categoryField)?.options} hideEmptyCategories={config.key === "articles"} onChange={changeClassification} collapsed={collapsed} onToggle={onToggle} /> : undefined}
      previewOpen={previewEnabled} onPreviewClose={closePreview}
      preview={hasPreview ? <LibraryPreview config={config} id={previewId} open={previewEnabled} editorOpen={creating || selectedId !== null} onClose={closePreview} onEdit={editRecord} onRefresh={refresh} /> : undefined}>
    <section className="panel data-panel" ref={panelRef} aria-busy={list.isFetching}>
      <div className={`toolbar${isTask ? " task-toolbar" : ""}`}><label className="search-field"><Search size={17} aria-hidden="true" /><span className="sr-only">{searchLabel}</span><input ref={searchInput} value={keyword} onChange={(event) => changeKeyword(event.target.value)} placeholder={searchLabel} /></label>
        {isTask && <div className="task-filters">
          {!taskArchive && <label><span className="sr-only">状态</span><select aria-label="筛选任务状态" value={status} onChange={(event) => { paginationTop.current = null; setStatus(event.target.value); if (event.target.value === "已完成") setOverdueOnly(false); setPage(1); }}><option value="">全部状态</option>{["待处理", "进行中", "已完成"].map((value) => <option key={value}>{value}</option>)}</select></label>}
          <label><span className="sr-only">优先级</span><select aria-label="筛选任务优先级" value={priority} onChange={(event) => { paginationTop.current = null; setPriority(event.target.value); setPage(1); }}><option value="">全部优先级</option>{["高", "中", "低"].map((value) => <option key={value} value={value}>{value}优先级</option>)}</select></label>
          {!taskArchive && <button className={`task-overdue-filter${overdueOnly ? " active" : ""}`} type="button" aria-pressed={overdueOnly} onClick={() => { paginationTop.current = null; setOverdueOnly((value) => !value); if (!overdueOnly && status === "已完成") setStatus(""); setPage(1); }}><AlertTriangle size={16} />仅看逾期</button>}
        </div>}
        {hasFavorites && <div className="list-filters"><label className="checkbox-label"><input type="checkbox" checked={favoriteOnly} onChange={(event) => { paginationTop.current = null; setFavoriteOnly(event.target.checked); setPage(1); }} />只看收藏</label></div>}
        {hasPreview && <button type="button" className={`button small preview-toggle${previewEnabled ? " active" : ""}`} aria-pressed={previewEnabled} disabled={previewId === null} title={previewId === null ? "点击卡片打开预览" : "点击同一卡片可收起预览"} onClick={() => togglePreview(previewId)}><PanelRight size={16} />预览</button>}
        <span className="result-count" aria-live="polite">{list.isPlaceholderData ? "正在加载…" : <>共 <strong>{list.data?.total ?? 0}</strong> {isCustomer ? "位客户" : "条记录"}</>}</span></div>
      {(database || category) && <div className="active-classification" role="group" aria-label="当前分类筛选">
        <div className="active-classification-tags">
          {database && <span className="active-classification-database" title={database}><DatabaseLabel name={database} /></span>}
          {category && <span className="active-classification-category" title={category}><FolderOpen size={14} aria-hidden="true" /><span>{category}</span></span>}
        </div>
        <button className="classification-clear" title="清除数据库和分类筛选" onClick={() => changeClassification("", "")}><RotateCcw size={14} aria-hidden="true" />清除分类</button>
      </div>}
      {notice && <div className={`alert${notification.error ? " error" : ""}`} role={notification.error ? "alert" : "status"}><span>{notification.error ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}{notice}</span><button className="icon-button" aria-label="关闭通知" onClick={() => setNotice("")}><X size={17} /></button></div>}
      {list.isLoading ? <TableSkeleton /> : list.error ? <ErrorState message="数据加载失败" retry={() => void list.refetch()} /> : !list.data?.items.length ? <EmptyState title={isTask && taskArchive ? "没有已归档任务" : `没有${config.title}数据`} description={isTask && taskArchive ? "已完成任务保留 15 天后自动归档，可在此查看或恢复。" : database || category || keyword ? "当前分类或搜索条件下没有记录，可切换分类、清空搜索或新增记录。" : "可通过右上角按钮创建第一条记录。"} /> : <>
        {hasFavorites ? <LibraryRecords config={config} rows={list.data.items} selectedId={previewEnabled ? previewId : null} disabled={list.isPlaceholderData} searchQuery={debouncedKeyword} onPreview={togglePreview} onEdit={editRecord} onUpdate={quickUpdate} onRemove={remove} onNotice={setNotice} /> : isCustomer ? <CustomerDirectory key={debouncedKeyword} searchQuery={debouncedKeyword} focus={projectTarget && jumpMode === "list" ? { customerId: projectCustomer, name: projectTarget, key: location.key } : null} rows={list.data.items} disabled={list.isPlaceholderData} onEdit={editRecord} onEditProject={setProjectEdit} onRemove={remove} /> : <div className="table-wrap"><table className={isTask ? "task-table" : undefined}><thead><tr>{config.columns.map((column) => <th key={column.name}>{column.label}</th>)}<th className="actions-heading"><span className="sr-only">操作</span></th></tr></thead><tbody>{list.data.items.map((row) => <tr className={isTask ? taskRowClass(row) : undefined} key={row.id}>{config.columns.map((column, index) => <td key={column.name} data-label={column.label}><span className={index === 0 ? "primary-cell" : undefined}>{index === 0 && config.fileLinks ? <LocalFileLinks row={row} label={String(row[column.name] ?? "")} config={config.fileLinks} disabled={list.isPlaceholderData} onNotice={setNotice} /> : isTask ? formatTaskCell(row, column.name) : formatCell(row[column.name], column.name)}</span></td>)}<td className="row-actions" data-label="操作">{hasFavorites && <button className="icon-button" aria-label={row.is_favorite ? "取消收藏" : "收藏"} disabled={list.isPlaceholderData} onClick={() => void quickUpdate(row, { is_favorite: row.is_favorite ? 0 : 1 })}><Star size={15} fill={row.is_favorite ? "currentColor" : "none"} /></button>}{config.key === "articles" && <button className="icon-button" aria-label={row.is_pinned ? "取消置顶" : "置顶"} disabled={list.isPlaceholderData} onClick={() => void quickUpdate(row, { is_pinned: row.is_pinned ? 0 : 1 })}><Pin size={15} fill={row.is_pinned ? "currentColor" : "none"} /></button>}{isTask && <button className="button small" disabled={list.isPlaceholderData} onClick={() => void quickUpdate(row, { status: row.status === "已完成" ? "待处理" : "已完成" })}>{row.status === "已完成" ? <><Undo2 size={14} />恢复</> : <><CheckCircle2 size={14} />完成</>}</button>}<button className="button small" disabled={list.isPlaceholderData} onClick={() => { setCreating(false); setSelectedId(row.id); }}><Pencil size={14} />查看/编辑</button><button className="button small danger" disabled={list.isPlaceholderData} onClick={() => void remove(row)}><Trash2 size={14} />删除</button></td></tr>)}</tbody></table></div>}
      </>}
      {list.data && !list.error && <Pagination page={list.data.page} pages={list.data.pages} total={list.data.total} pageSize={pageSize} onChange={changePage} onPageSizeChange={(size) => { clearProjectTarget(); paginationTop.current = null; setPageSize(size); setPage(1); }} />}
    </section>
    </LibraryLayout>
    {projectTarget && jumpMode === "drawer" && <CustomerProjectDrawer customerId={projectCustomer} projectName={projectTarget}
      returnFocus={searchInput} onClose={clearProjectTarget} />}
    {projectEdit && <CustomerProjectEditor selection={projectEdit}
      onClose={() => setProjectEdit(null)}
      onRefresh={() => { setProjectEdit(null); void refresh(); }}
      onSaved={() => {
        setProjectEdit((current) => current === projectEdit ? null : current);
        setNotice("项目已更新");
        void refresh();
      }} />}
    {(creating || selectedId !== null) && <Editor
      key={creating ? "new" : `${selectedId}-${detail.data?.revision ?? "loading"}`}
      config={editorConfig}
      item={creating ? undefined : detail.data}
      loading={!creating && detail.isLoading}
      editing={!creating}
      useNativeDialog={hasPreview}
      loadError={!creating && !!detail.error}
      onRetry={() => void detail.refetch()}
      onRefresh={refresh}
      onClose={closeEditor}
      onSave={save}
    />}
  </div>;
}

function Editor({ config, item, loading, editing, useNativeDialog, loadError, onRetry, onRefresh, onClose, onSave }: {
  config: CrudConfig;
  item?: Entity;
  loading: boolean;
  editing: boolean;
  useNativeDialog: boolean;
  loadError: boolean;
  onRetry: () => void;
  onRefresh: () => Promise<void>;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>, current?: Entity) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const isCustomer = config.key === "customers";
  const [draft, setDraft] = useState(() => makeCustomerDraft(isCustomer ? item : undefined));
  const native = useNativeDialog && typeof HTMLDialogElement.prototype.showModal === "function";
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, [native]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {};
    for (const field of config.fields) {
      const raw = String(data.get(field.name) ?? "");
      payload[field.name] = field.type === "number" ? Number(raw || 0) : raw;
    }
    if (isCustomer) payload.project_profile = customerProfilePayload(draft);
    try { await onSave(payload, item); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "保存失败"); }
    finally { setBusy(false); }
  }
  const saveError = error && <div className="alert error full" role="alert">{error}</div>;
  const actions = <div className="modal-actions full"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy ? "保存中…" : <><CheckCircle2 size={17} />保存</>}</button></div>;
  const content = <section className={`modal${isCustomer ? " customer-modal" : ""}`} role={native ? undefined : "dialog"} aria-modal={native ? undefined : true} aria-labelledby={native ? undefined : "editor-title"}
    onKeyDown={(event) => {
      if (config.key !== "scripts" || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
      event.preventDefault();
      if (!busy) event.currentTarget.querySelector("form")?.requestSubmit();
    }}>
      <div className="modal-header"><div><p className="eyebrow">{editing ? "EDIT RECORD" : "CREATE RECORD"}</p><h2 id="editor-title">{editing ? `编辑${config.title}` : `新增${config.title}`}</h2></div><button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button></div>
      {loading ? <LoadingState /> : loadError || (editing && !item) ? <ErrorState message="详情加载失败，未进入新增模式，请重试" retry={onRetry} /> : isCustomer ? <form className="customer-edit-form" onSubmit={submit}>
        <div className="customer-edit-content form-grid"><CustomerFields item={item} draft={draft} setDraft={setDraft} /></div>
        <footer className="customer-edit-footer">{saveError}{actions}</footer>
      </form> : <form className="form-grid" onSubmit={submit}>
        {config.fields.map((field) => <FieldInput key={field.name} field={field} value={item?.[field.name]} />)}
        {saveError}{actions}
      </form>}
      {item && !loading && !loadError && <EntityDetails module={config.key} item={item} onRefresh={onRefresh} />}
    </section>;
  return native ? <dialog ref={dialogRef} className="modal-backdrop library-editor-backdrop" aria-labelledby="editor-title"
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>{content}</dialog>
    : <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>{content}</div>;
}

function FieldInput({ field, value }: { field: Field; value: unknown }) {
  const initial = value === null || value === undefined ? field.defaultValue ?? "" : String(value);
  const options = [...new Set([...(field.options ?? []), String(initial)])];
  return <label className={field.type === "textarea" ? "full" : undefined}>{field.label}
    {field.type === "textarea" ? <textarea name={field.name} aria-label={field.label} defaultValue={String(initial)} rows={field.name === "content" ? 12 : 4} required={field.required} />
      : field.type === "date" ? <DateField name={field.name} label={field.label} initialValue={String(initial)} required={field.required} />
      : field.type === "select" ? <select name={field.name} aria-label={field.label} defaultValue={String(initial)} required={field.required} title={String(initial)} onChange={(event) => { event.currentTarget.title = event.currentTarget.value; }}>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select>
      : <><input name={field.name} aria-label={field.label} type={field.type ?? "text"} defaultValue={String(initial)} required={field.required} list={field.options?.length ? `field-${field.name}-options` : undefined} />{field.options?.length ? <datalist id={`field-${field.name}-options`}>{field.options.map((option) => <option key={option} value={option} />)}</datalist> : null}</>}
  </label>;
}

function formatCell(value: unknown, field: string) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  const text = String(value);
  if (field === "status") return <span className={`badge status-${statusTone(text)}`}>{text}</span>;
  if (field === "priority") return <span className={`badge priority-${text}`}>{text}</span>;
  return text;
}

function taskRowClass(row: Entity) {
  const priority = row.priority === "高" ? "high" : row.priority === "低" ? "low" : "medium";
  return `task-row task-priority-${priority}${row.is_overdue ? " is-overdue" : ""}${row.status === "已完成" ? " is-completed" : ""}`;
}

function formatTaskCell(row: Entity, field: string) {
  if (field === "title") return <span className="task-title-cell"><strong>{String(row.title ?? "未命名任务")}</strong>{row.description ? <small>{String(row.description)}</small> : null}</span>;
  if (field === "priority") {
    const priority = String(row.priority ?? "中");
    const tone = priority === "高" ? "high" : priority === "低" ? "low" : "medium";
    const Icon = tone === "high" ? ChevronsUp : tone === "low" ? ChevronDown : Minus;
    return <span className={`task-priority-badge ${tone}`} title={`${priority}优先级`}><Icon size={14} aria-hidden="true" />{priority}</span>;
  }
  if (field === "status") return <span className="task-state-cell">{row.is_overdue ? <span className="badge status-danger"><AlertTriangle size={13} />已逾期</span> : null}{formatCell(row.is_archived ? "已归档" : row.status, "status")}</span>;
  if (field === "due_date") {
    if (!row.due_date) return <span className="muted">未设置</span>;
    const date = String(row.due_date);
    return <span className={`task-due-cell${row.is_overdue ? " overdue" : ""}`}><span><CalendarDays size={14} />{date}</span>{row.is_overdue ? <small>已逾期 {overdueDays(date)} 天</small> : null}</span>;
  }
  return formatCell(row[field], field);
}

function overdueDays(value: string) {
  const due = new Date(`${value}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(1, Math.floor((today.getTime() - due.getTime()) / 86_400_000));
}

function statusTone(value: string) {
  if (["已完成", "活跃", "已结束"].includes(value)) return "success";
  if (["已暂停", "逾期"].includes(value)) return "danger";
  return "info";
}
