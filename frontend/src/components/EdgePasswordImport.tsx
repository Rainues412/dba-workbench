import { useEffect, useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import { api, ApiError, jsonBody } from "../api/client";
import { decryptSecret, encryptSecret } from "../vault/crypto";
import type { VaultCipherItem, VaultSecret } from "../vault/crypto";
import { edgeImportKey, loginIdentity, parseEdgeCsv } from "../vault/edgeCsv";

export function EdgePasswordImport({ dek, userId, canImport, loadExisting, onImported }: {
  dek: Uint8Array<ArrayBuffer>;
  userId: number;
  canImport: () => boolean;
  loadExisting: () => Promise<VaultSecret[]>;
  onImported: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [parsed, setParsed] = useState<ReturnType<typeof parseEdgeCsv> | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const active = useRef(true);
  const generation = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const allowed = useRef(canImport); allowed.current = canImport;
  const request = useRef<AbortController | null>(null);
  useEffect(() => { active.current = true; return () => { active.current = false; generation.current += 1; request.current?.abort(); }; }, []);
  function check() { if (!active.current || !allowed.current()) throw new Error("保险箱已锁定或敏感操作授权已过期，请重新验证后重试"); }
  function clearFile() { if (fileInput.current) fileInput.current.value = ""; }
  function close() { if (busy) return; generation.current += 1; clearFile(); setParsed(null); setMessage(""); setError(""); setOpen(false); }
  async function read(file?: File) {
    const current = ++generation.current;
    setParsed(null); setError(""); setMessage("");
    if (!file) return;
    try {
      check();
      if (file.size > 10 * 1024 * 1024) throw new Error("CSV 文件超过 10MB，请分批导出");
      const bytes = await file.arrayBuffer();
      check();
      if (current !== generation.current) return;
      let text = "";
      try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
      catch { throw new Error("文件不是有效 UTF-8，请重新从 Edge 导出，避免密码被错误转码"); }
      setParsed(parseEdgeCsv(text));
    } catch (reason) { if (active.current && current === generation.current) setError(reason instanceof Error ? reason.message : "CSV 读取失败"); }
  }
  async function importPasswords() {
    if (!parsed || busy) return;
    setBusy(true); setError(""); setMessage("");
    let imported = 0, skipped = 0;
    request.current = new AbortController();
    try {
      check();
      const known = new Set((await loadExisting()).map(loginIdentity));
      check();
      for (const secret of parsed.items) {
        check();
        const identity = loginIdentity(secret);
        if (known.has(identity)) { skipped += 1; continue; }
        const key = await edgeImportKey(dek, secret);
        check();
        const envelope = await encryptSecret(dek, userId, secret, key);
        check();
        let saved: VaultCipherItem;
        try { saved = await api<VaultCipherItem>("/api/vault/items", { method: "POST", body: jsonBody(envelope), signal: request.current.signal }); }
        catch (reason) {
          if (!(reason instanceof ApiError && reason.status === 409)) throw reason;
          check();
          if ((await loadExisting()).some((entry) => loginIdentity(entry) === identity)) { known.add(identity); skipped += 1; continue; }
          throw new Error("存在已被修改的同源导入条目，未覆盖现有记录，请人工核对后重试");
        }
        check();
        if (loginIdentity(await decryptSecret(dek, saved)) !== identity) throw new Error("导入回读校验失败，请保留 CSV 并核对保险箱");
        known.add(identity); imported += 1;
        if (active.current) setMessage(`已验证导入 ${imported} 条，跳过重复 ${skipped} 条…`);
      }
      check();
      setMessage(`导入完成：新增 ${imported} 条，跳过重复 ${skipped} 条，无密码行 ${parsed.emptyPasswords} 条。核对保险箱后，请自行删除明文 CSV。`);
      clearFile();
      setParsed(null);
    } catch {
      // Do not reflect API response text: it must never echo credential data.
      if (active.current) setError(`导入已暂停：已确认新增 ${imported} 条，跳过 ${skipped} 条。请检查授权及服务状态；最后一条可能已提交，可安全重试，不会覆盖现有条目。`);
    } finally {
      if (active.current) {
        setBusy(false);
        try { await onImported(); } catch { setError("导入结束，但列表刷新失败。请保留 CSV 并刷新后核对，不要删除原文件。"); }
      }
    }
  }
  return <><button className="button" disabled={busy} onClick={() => { if (canImport()) setOpen(true); else setError("请先重新验证登录密码并解锁保险箱"); }}><Upload size={16} />导入 Edge 密码</button>{error && !open && <p role="alert">{error}</p>}{open && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="edge-import-title"><div className="modal-header"><h2 id="edge-import-title">导入 Edge 密码 CSV</h2><button className="icon-button" aria-label="关闭 Edge 导入" disabled={busy} onClick={close}><X size={19} /></button></div><p className="muted">CSV 是明文文件。只在本机浏览器内解析和加密，不上传原文件、不保存到 localStorage、不显示密码预览。</p><p className="muted">相同网址、账号和密码会跳过；密码不同另存为新条目，不覆盖现有记录。导入分类为“Edge 导入”。</p><label>选择 Edge CSV<input ref={fileInput} type="file" accept=".csv,text/csv" disabled={busy} onClick={(event) => { event.currentTarget.value = ""; }} onChange={(event) => { void read(event.target.files?.[0]); }} /></label>{parsed && <p role="status">待导入 {parsed.items.length} 条，无密码行 {parsed.emptyPasswords} 条。点击确认后才写入。</p>}{message && <p className="alert" role="status">{message}</p>}{error && <p className="alert error" role="alert">{error}</p>}<div className="modal-actions"><button className="button" disabled={busy} onClick={close}>关闭</button><button className="button primary" disabled={busy || !parsed} onClick={() => void importPasswords()}>{busy ? "正在加密导入…" : "确认加密导入"}</button></div></section></div>}</>;
}
