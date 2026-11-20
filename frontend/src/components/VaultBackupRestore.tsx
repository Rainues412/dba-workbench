import { useId, useRef, useState } from "react";
import { AlertTriangle, Download, Upload, X } from "lucide-react";
import { AppDialog } from "./AppDialog";
import { DialogFocusBoundary } from "./DialogFocusBoundary";

export function VaultBackupRestore({ canRestore, onBackup, onRestore }: {
  canRestore: () => boolean;
  onBackup: () => Promise<void>;
  onRestore: (file: File) => Promise<void>;
}) {
  const headingId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function close() { if (!busy) { setFile(null); setError(""); setNotice(""); } }

  return <>
    <button type="button" className="button" onClick={() => { if (canRestore()) input.current?.click(); }}><Upload size={16} />恢复备份</button>
    <input ref={input} className="sr-only" type="file" accept="application/json,.json" aria-label="选择加密备份" tabIndex={-1} disabled={busy} onChange={(event) => {
      const selected = event.target.files?.[0];
      event.target.value = "";
      if (selected && canRestore()) { setFile(selected); setError(""); setNotice(""); }
    }} />
    {file && <AppDialog className="modal vault-restore-dialog" labelledBy={headingId} onClose={close}>
      <DialogFocusBoundary><div className="modal-header"><h2 id={headingId}>恢复加密备份</h2><button type="button" className="icon-button" aria-label="关闭恢复" disabled={busy} onClick={close}><X size={19} /></button></div>
      <div className="backup-file"><strong title={file.name}>{file.name}</strong><button type="button" className="button small" disabled={busy} onClick={() => input.current?.click()}>重新选择</button></div>
      <div className="consequence-warning"><AlertTriangle size={19} aria-hidden="true" /><div><strong>恢复会替换当前保险箱全部密文，现有条目将被备份内容覆盖。</strong><p>建议先导出当前加密备份。</p></div></div>
      <button type="button" className="button" disabled={busy} onClick={async () => {
        setBusy(true); setError(""); setNotice("");
        try { await onBackup(); setNotice("当前保险箱备份已生成，请确认文件已保存。"); }
        catch (reason) { setError(reason instanceof Error ? reason.message : "备份失败，请重试"); }
        finally { setBusy(false); }
      }}><Download size={16} />先备份当前保险箱</button>
      <details className="context-details"><summary>恢复步骤与校验</summary><p>恢复后保险箱会锁定，请使用备份对应的主密码重新解锁并核对条目。</p></details>
      {notice && <p role="status" className="alert">{notice}</p>}
      {error && <p role="alert" className="alert error">{error}</p>}
      <div className="modal-actions"><button type="button" className="button" disabled={busy} onClick={close}>取消</button><button type="button" className="button primary" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try { await onRestore(file); setFile(null); setNotice(""); }
        catch (reason) { setError(reason instanceof Error ? reason.message : "备份恢复失败"); }
        finally { setBusy(false); }
      }}>{busy ? "处理中…" : "确认恢复"}</button></div>
      </DialogFocusBoundary></AppDialog>}
  </>;
}
