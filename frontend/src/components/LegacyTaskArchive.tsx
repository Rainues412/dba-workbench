import { useState } from "react";
import { Archive, X } from "lucide-react";
import { api, jsonBody } from "../api/client";

const KEY = "wb_dba_workbench_tasks_archive";
type Entry = { id?: string | number | null; title: string; notes?: string; priority?: string; deadline?: string | null; completedAt?: string | null };

export function LegacyTaskArchive({ onImported }: { onImported: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  function show() {
    setOpen(true); setMessage(""); setEntries([]);
    try {
      const value: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
      if (!Array.isArray(value) || value.some((entry) => !entry || typeof entry !== "object" || typeof entry.title !== "string"
        || ["notes", "priority"].some((field) => entry[field] !== undefined && typeof entry[field] !== "string")
        || ["deadline", "completedAt"].some((field) => entry[field] != null && typeof entry[field] !== "string")
        || (entry.id != null && typeof entry.id !== "string" && typeof entry.id !== "number"))) throw new Error("旧归档格式无效，源数据未修改");
      setEntries(value);
    } catch { setMessage("无法读取旧归档，源数据未修改"); }
  }
  async function migrate() {
    if (!window.confirm(`将 ${entries.length} 条旧归档追加为已完成任务？原浏览器数据保留，重复导入会跳过已迁移记录。`)) return;
    setBusy(true); setMessage("");
    let imported = 0, skipped = 0;
    try {
      for (let index = 0; index < entries.length; index += 200) {
        const response = await api<{ imported: number; skipped: number }>("/api/tasks/legacy-archive", { method: "POST", body: jsonBody({ items: entries.slice(index, index + 200) }) });
        imported += response.imported; skipped += response.skipped;
      }
      setMessage(`已导入 ${imported} 条，跳过已迁移 ${skipped} 条。原归档保留；在任务状态“已完成”下查看或恢复。`);
    } catch (error) { setMessage(`本次已导入 ${imported} 条，后续失败：${error instanceof Error ? error.message : "请求失败"}。可安全重试，原归档未清理。`); }
    finally { setBusy(false); await onImported(); }
  }
  return <><button className="button" onClick={show}><Archive size={16} />旧任务归档</button>{open && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="legacy-task-title"><div className="modal-header"><h2 id="legacy-task-title">旧任务归档迁移</h2><button className="icon-button" aria-label="关闭归档" disabled={busy} onClick={() => setOpen(false)}><X size={18} /></button></div><p className="muted">仅能读取当前浏览器、当前地址下的旧归档。未发现记录不代表其他浏览器或 localhost/127.0.0.1 地址下没有数据。不会自动清理或删除原归档。</p><p>发现 {entries.length} 条旧归档</p><ul className="detail-list">{entries.slice(0, 50).map((entry, index) => <li key={index}><strong>{entry.title}</strong><span>{entry.completedAt?.slice(0, 10) ?? "无完成日期"} · {entry.priority ?? "P1"}</span></li>)}</ul>{entries.length > 50 && <p className="muted">仅预览前 50 条，导入包含全部记录。</p>}{message && <p role="status" className="alert">{message}</p>}<div className="modal-actions"><button className="button primary" disabled={busy || !entries.length} onClick={() => void migrate()}>{busy ? "迁移中…" : "追加导入已完成任务"}</button></div></section></div>}</>;
}
