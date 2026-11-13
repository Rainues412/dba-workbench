import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, Entity, entityApi } from "../api/client";
import { ErrorState, LoadingState } from "./States";

export function EntityDetails({ module, item, onRefresh, readOnly = false }: { module: string; item: Entity; onRefresh: () => Promise<void>; readOnly?: boolean }) {
  if (module === "scripts") return <ScriptHistory item={item} onRefresh={onRefresh} readOnly={readOnly} />;
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
