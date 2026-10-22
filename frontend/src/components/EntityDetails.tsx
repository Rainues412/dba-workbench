import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Entity, entityApi, jsonBody } from "../api/client";
import { ErrorState, LoadingState } from "./States";

export function EntityDetails({ module, item, onRefresh, readOnly = false }: { module: string; item: Entity; onRefresh: () => Promise<void>; readOnly?: boolean }) {
  if (module === "scripts") return <ScriptHistory item={item} onRefresh={onRefresh} readOnly={readOnly} />;
  if (module === "customers") return <CustomerRelations item={item} onRefresh={onRefresh} />;
  return null;
}

function ScriptHistory({ item, onRefresh, readOnly }: { item: Entity; onRefresh: () => Promise<void>; readOnly: boolean }) {
  const versions = (item.versions ?? []) as { version: number; created_at: string }[];
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const history = useQuery({ queryKey: ["scripts", "version", item.id, version], queryFn: () => api<{ content: string }>(`/api/scripts/${item.id}/versions/${version}`), enabled: !!version });
  async function restore() {
    if (!history.data || !window.confirm(`恢复版本 ${version} 为当前正文？将立即保存并保留当前正文的历史版本；表单中尚未保存的改动将被丢弃。`)) return;
    setBusy(true); setMessage("");
    try { await entityApi.update("/api/scripts/", item.id, item.revision, { content: history.data.content }); await onRefresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "恢复失败"); }
    finally { setBusy(false); }
  }
  return <section className="entity-details"><h3>脚本历史版本</h3><p className="muted">当前版本 {String(item.version ?? 1)}。正文变更时自动保存历史；不会执行脚本。</p>{!versions.length ? <p className="muted">暂无历史版本</p> : <><label>查看历史版本<select value={version} onChange={(event) => setVersion(event.target.value)}><option value="">请选择版本</option>{versions.map((row) => <option key={row.version} value={row.version}>版本 {row.version} · {row.created_at}</option>)}</select></label>{version && (history.isLoading ? <LoadingState /> : history.error ? <ErrorState message="历史版本加载失败" retry={() => void history.refetch()} /> : <><label>历史正文<textarea readOnly value={history.data?.content ?? ""} rows={8} /></label>{!readOnly && <button className="button" type="button" disabled={busy || !history.data} onClick={() => void restore()}>恢复此版本为当前正文</button>}</>)}</>}{message && <p className="alert error" role="alert">{message}</p>}</section>;
}

function CustomerRelations({ item, onRefresh }: { item: Entity; onRefresh: () => Promise<void> }) {
  const contacts = (item.contacts ?? []) as Entity[];
  const communications = (item.communications ?? []) as Entity[];
  const tasks = (item.tasks ?? []) as Entity[];
  const [contact, setContact] = useState<Entity | null | "new">(null);
  const [addingComm, setAddingComm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function mutate(path: string, method: string, body?: Record<string, unknown>) {
    setBusy(true); setMessage("");
    try { await api(path, { method, ...(body ? { body: jsonBody(body) } : {}) }); setContact(null); setAddingComm(false); await onRefresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
    finally { setBusy(false); }
  }
  function saveContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(["name", "role", "phone", "wechat", "notes"].map((field) => [field, String(data.get(field) ?? "")]));
    void mutate(contact && contact !== "new" ? `/api/customers/contacts/${contact.id}` : `/api/customers/${item.id}/contacts`, contact && contact !== "new" ? "PUT" : "POST", payload);
  }
  function saveComm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void mutate(`/api/customers/${item.id}/communications`, "POST", Object.fromEntries(["date", "content", "follow_up"].map((field) => [field, String(data.get(field) ?? "")])));
  }
  return <section className="entity-details customer-relations" aria-label="客户关联信息">
    <section className="customer-relation-panel" aria-labelledby={`customer-contacts-${item.id}`}>
      <div className="section-heading"><h3 id={`customer-contacts-${item.id}`}>关联联系人 <span className="badge">{contacts.length}</span></h3><button type="button" className="button small" disabled={busy} onClick={() => setContact("new")}>新增联系人</button></div>
      <ul className="detail-list customer-contact-list">{contacts.map((row) => <li key={row.id}>
        <div className="customer-contact-heading"><strong title={String(row.name)}>{String(row.name)}</strong>{Boolean(row.role) && <span className="badge">{String(row.role)}</span>}</div>
        <dl className="customer-contact-facts"><div><dt>电话</dt><dd>{String(row.phone || "未填写")}</dd></div><div><dt>微信</dt><dd>{String(row.wechat || "未填写")}</dd></div></dl>
        {Boolean(row.notes) && <p className="muted">{String(row.notes)}</p>}
        <div className="button-row"><button className="button small" disabled={busy} onClick={() => setContact(row)}>编辑联系人</button><button className="button small danger" disabled={busy} onClick={() => { if (window.confirm("确定删除此联系人？")) void mutate(`/api/customers/contacts/${row.id}`, "DELETE"); }}>删除联系人</button></div>
      </li>)}</ul>
      {!contacts.length && <p className="customer-relation-empty muted">暂无联系人</p>}
      {contact && <form className="form-grid customer-related-form" key={contact === "new" ? "new" : contact.id} onSubmit={saveContact}>{[["name", "姓名"], ["role", "角色"], ["phone", "电话"], ["wechat", "微信"], ["notes", "备注"]].map(([field, label]) => <label className={field === "notes" ? "full" : undefined} key={field}>{label}<input name={field} defaultValue={contact === "new" ? "" : String(contact[field] ?? "")} required={field === "name"} /></label>)}<div className="modal-actions full"><button type="button" className="button" onClick={() => setContact(null)} disabled={busy}>取消</button><button className="button primary" disabled={busy}>保存联系人</button></div></form>}
    </section>
    <section className="customer-relation-panel" aria-labelledby={`customer-communications-${item.id}`}>
      <div className="section-heading"><h3 id={`customer-communications-${item.id}`}>沟通记录 <small className="muted">最近 50 条</small></h3><button type="button" className="button small" disabled={busy} onClick={() => setAddingComm(true)}>新增沟通记录</button></div>
      <ul className="detail-list customer-communication-list">{communications.map((row) => <li key={row.id}>
        <div><time dateTime={String(row.date)}>{String(row.date)}</time><p>{String(row.content)}</p>{Boolean(row.follow_up) && <p className="muted">跟进：{String(row.follow_up)}</p>}</div>
        <button className="button small danger" disabled={busy} onClick={() => { if (window.confirm("确定删除此沟通记录？")) void mutate(`/api/customers/communications/${row.id}`, "DELETE"); }}>删除沟通记录</button>
      </li>)}</ul>
      {!communications.length && <p className="customer-relation-empty muted">暂无沟通记录</p>}
      {addingComm && <form className="form-grid customer-related-form" onSubmit={saveComm}><label className="full">日期<input name="date" type="date" required /></label><label className="full">沟通内容<textarea name="content" required /></label><label className="full">后续跟进<textarea name="follow_up" /></label><div className="modal-actions full"><button type="button" className="button" disabled={busy} onClick={() => setAddingComm(false)}>取消</button><button className="button primary" disabled={busy}>保存沟通记录</button></div></form>}
    </section>
    <section className="customer-relation-panel customer-task-panel" aria-labelledby={`customer-tasks-${item.id}`}>
      <div className="section-heading"><h3 id={`customer-tasks-${item.id}`}>关联任务 <span className="badge">{tasks.length}</span></h3></div>
      <ul className="detail-list">{tasks.map((row) => <li key={row.id}><Link title={String(row.title)} to={`/tasks?record=${row.id}`}>{String(row.title)}</Link><span className="muted">{String(row.priority)} · {String(row.status)}</span></li>)}</ul>{!tasks.length && <p className="customer-relation-empty muted">暂无关联任务</p>}
    </section>
    {message && <p role="alert" className="alert error full">{message}</p>}
  </section>;
}
