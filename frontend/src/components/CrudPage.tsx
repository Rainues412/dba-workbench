import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ApiError, Entity, entityApi } from "../api/client";
import { EmptyState, ErrorState, LoadingState, TableSkeleton } from "./States";

export type Field = {
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
};

export function CrudPage({ config }: { config: CrudConfig }) {
  const PageIcon = config.icon;
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const list = useQuery({
    queryKey: [config.key, page, keyword],
    queryFn: () => entityApi.list<Entity>(config.path, page, keyword),
  });
  const detail = useQuery({
    queryKey: [config.key, "detail", selectedId],
    queryFn: () => entityApi.detail<Entity>(config.path, selectedId!),
    enabled: selectedId !== null,
  });

  function closeEditor() { setSelectedId(null); setCreating(false); }
  async function refresh() {
    await client.invalidateQueries({ queryKey: [config.key] });
  }

  async function save(payload: Record<string, unknown>, current?: Entity) {
    try {
      if (current) await entityApi.update(config.path, current.id, current.revision, payload);
      else await entityApi.create(config.path, payload);
      setNotice(current ? "记录已更新" : "记录已创建");
      closeEditor();
      await refresh();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409 && current) {
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
      setNotice("记录已删除");
      await refresh();
    } catch (reason) {
      setNotice(reason instanceof ApiError ? reason.message : "删除失败");
    }
  }

  return <div className="page">
    <header className="page-header"><div className="page-title-group"><span className="page-title-icon"><PageIcon size={24} /></span><div><p className="eyebrow">DATA MODULE</p><h1>{config.title}</h1><p className="muted">{config.description}</p></div></div><button className="button primary" onClick={() => setCreating(true)}><Plus size={17} />新增</button></header>
    <section className="panel data-panel">
      <div className="toolbar"><label className="search-field"><Search size={17} aria-hidden="true" /><span className="sr-only">搜索{config.title}</span><input value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} placeholder={`搜索${config.title}`} /></label><span className="result-count">共 <strong>{list.data?.total ?? 0}</strong> 条记录</span></div>
      {notice && <div className="alert" role="status"><span><CheckCircle2 size={17} />{notice}</span><button className="icon-button" aria-label="关闭通知" onClick={() => setNotice("")}><X size={17} /></button></div>}
      {list.isLoading ? <TableSkeleton /> : list.error ? <ErrorState message="数据加载失败" retry={() => void list.refetch()} /> : !list.data?.items.length ? <EmptyState title={`没有${config.title}数据`} description="可通过右上角按钮创建第一条记录。" /> : <>
        <div className="table-wrap"><table><thead><tr>{config.columns.map((column) => <th key={column.name}>{column.label}</th>)}<th className="actions-heading"><span className="sr-only">操作</span></th></tr></thead><tbody>{list.data.items.map((row) => <tr key={row.id}>{config.columns.map((column, index) => <td key={column.name} data-label={column.label}><span className={index === 0 ? "primary-cell" : undefined}>{formatCell(row[column.name], column.name)}</span></td>)}<td className="row-actions" data-label="操作"><button className="button small" onClick={() => setSelectedId(row.id)}><Pencil size={14} />查看/编辑</button><button className="button small danger" onClick={() => void remove(row)}><Trash2 size={14} />删除</button></td></tr>)}</tbody></table></div>
        <div className="pagination"><span className="page-indicator">第 <strong>{list.data.page}</strong> / {list.data.pages || 1} 页</span><div><button className="button pagination-button" aria-label="上一页" disabled={!list.data.has_previous} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={17} />上一页</button><button className="button pagination-button" aria-label="下一页" disabled={!list.data.has_next} onClick={() => setPage((value) => value + 1)}>下一页<ChevronRight size={17} /></button></div></div>
      </>}
    </section>
    {(creating || selectedId !== null) && <Editor
      key={creating ? "new" : `${selectedId}-${detail.data?.revision ?? "loading"}`}
      config={config}
      item={creating ? undefined : detail.data}
      loading={!creating && detail.isLoading}
      onClose={closeEditor}
      onSave={save}
    />}
  </div>;
}

function Editor({ config, item, loading, onClose, onSave }: {
  config: CrudConfig;
  item?: Entity;
  loading: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>, current?: Entity) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {};
    for (const field of config.fields) {
      const raw = String(data.get(field.name) ?? "");
      payload[field.name] = field.type === "number" ? Number(raw || 0) : raw;
    }
    try { await onSave(payload, item); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="editor-title">
      <div className="modal-header"><div><p className="eyebrow">{item ? "EDIT RECORD" : "CREATE RECORD"}</p><h2 id="editor-title">{item ? `编辑${config.title}` : `新增${config.title}`}</h2></div><button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button></div>
      {loading ? <LoadingState /> : <form className="form-grid" onSubmit={submit}>
        {config.fields.map((field) => <FieldInput key={field.name} field={field} value={item?.[field.name]} />)}
        {error && <div className="alert error full" role="alert">{error}</div>}
        <div className="modal-actions full"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy ? "保存中…" : <><CheckCircle2 size={17} />保存</>}</button></div>
      </form>}
    </section>
  </div>;
}

function FieldInput({ field, value }: { field: Field; value: unknown }) {
  const initial = value === null || value === undefined ? field.defaultValue ?? "" : String(value);
  return <label className={field.type === "textarea" ? "full" : undefined}>{field.label}
    {field.type === "textarea" ? <textarea name={field.name} defaultValue={String(initial)} rows={field.name === "content" ? 12 : 4} required={field.required} />
      : field.type === "select" ? <select name={field.name} defaultValue={String(initial)} required={field.required}>{field.options?.map((option) => <option key={option}>{option}</option>)}</select>
      : <input name={field.name} type={field.type ?? "text"} defaultValue={String(initial)} required={field.required} />}
  </label>;
}

function formatCell(value: unknown, field: string) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  const text = String(value);
  if (field === "status") return <span className={`badge status-${statusTone(text)}`}>{text}</span>;
  if (field === "priority") return <span className={`badge priority-${text}`}>{text}</span>;
  return text;
}

function statusTone(value: string) {
  if (["已完成", "活跃", "已结束"].includes(value)) return "success";
  if (["已暂停", "逾期"].includes(value)) return "danger";
  return "info";
}
