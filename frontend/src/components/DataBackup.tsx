import { useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { DatabaseBackup, Download, Upload, X } from "lucide-react";
import { api, jsonBody } from "../api/client";

const tables = ["scripts", "script_versions", "articles", "tasks", "customers", "contacts", "communications", "resources"];
const tableLabels: Record<string, string> = { scripts: "脚本", script_versions: "脚本历史", articles: "知识", tasks: "任务", customers: "客户", contacts: "联系人", communications: "沟通记录", resources: "资源" };
type Backup = Record<string, unknown>;
type ImportResult = { ok: boolean; imported: Record<string, number>; errors: unknown[] };

export function DataBackup() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [backup, setBackup] = useState<Backup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function selectFile(file?: File) {
    setBackup(null); setError(""); setNotice("");
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("备份必须是 JSON 对象");
      const value = parsed as Backup;
      if (!tables.some((table) => table in value)) throw new Error("未识别到普通模块备份；保险箱请使用其专用加密备份入口");
      for (const table of tables) {
        if (table in value && (!Array.isArray(value[table]) || (value[table] as unknown[]).some((row) => !row || typeof row !== "object" || Array.isArray(row)))) {
          throw new Error(`${tableLabels[table]}数据必须是记录数组`);
        }
      }
      setBackup(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "备份读取失败"); }
  }

  async function exportBackup() {
    setBusy(true); setError(""); setNotice("");
    try {
      const data = await api<Backup>("/api/export/all");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = `dba-workbench-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("普通模块备份已下载，包含数据库中的正文，不打包原路径文件或保险箱。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导出失败"); }
    finally { setBusy(false); }
  }

  async function importBackup() {
    if (!backup || !window.confirm("确认追加导入此备份？现有记录不会被覆盖或删除；重复导入将产生重复记录。")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<ImportResult>("/api/export/import", { method: "POST", body: jsonBody({ data: backup }) });
      if (!result.ok || result.errors?.length) throw new Error("导入结果含错误，请核查后重试，勿重复追加导入。");
      setBackup(null);
      setNotice(`追加导入完成：${Object.entries(result.imported).map(([table, count]) => `${tableLabels[table] ?? table} ${count} 条`).join("、")}。现有记录保持不变。`);
      for (const key of ["scripts", "articles", "tasks", "customers", "resources", "dashboard", "global-search"]) {
        void client.invalidateQueries({ queryKey: [key] });
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); }
    finally { setBusy(false); }
  }

  return <>
    <button className="icon-button topbar-button" aria-label="普通数据备份" title="普通数据备份" onClick={() => setOpen(true)}><DatabaseBackup size={18} /></button>
    {open && createPortal(<div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (!busy && event.target === event.currentTarget) setOpen(false); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="data-backup-title">
        <div className="modal-header"><div><p className="eyebrow">DATA BACKUP</p><h2 id="data-backup-title">普通模块备份与导入</h2></div><button className="icon-button" aria-label="关闭备份" disabled={busy} onClick={() => setOpen(false)}><X size={19} /></button></div>
        <div className="form-grid">
          <p className="muted full">包含脚本、知识及其数据库正文、任务、客户及关联记录、资源索引。不打包原路径文件，不包含保险箱和账户；JSON 中可能含敏感业务信息，请妥善保管。</p>
          <div className="full"><button className="button" disabled={busy} onClick={() => void exportBackup()}><Download size={17} />导出 JSON 备份</button></div>
          <label className="full">选择普通模块 JSON 备份<input aria-label="选择备份文件" type="file" accept=".json,application/json" disabled={busy} onChange={(event) => void selectFile(event.target.files?.[0])} /></label>
          <p className="muted full">导入为追加，不是覆盖恢复。现有数据不变；重复导入会产生重复记录。任一记录失败时，本次导入全部回滚。</p>
          {backup && <p className="full" role="status">待追加：{tables.filter((table) => Array.isArray(backup[table])).map((table) => `${tableLabels[table]} ${(backup[table] as unknown[]).length} 条`).join("、")}</p>}
          {error && <div className="alert error full" role="alert">{error}</div>}
          {notice && <div className="alert full" role="status">{notice}</div>}
          <div className="modal-actions full"><button className="button" disabled={busy} onClick={() => setOpen(false)}>关闭</button><button className="button primary" disabled={busy || !backup} onClick={() => void importBackup()}><Upload size={17} />{busy ? "处理中…" : "确认追加导入"}</button></div>
        </div>
      </section>
    </div>, document.body)}
  </>;
}
