import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, RotateCcw, Upload, X } from "lucide-react";
import { api, hasVaultAccessToken, jsonBody, setVaultAccessToken, VAULT_LOCKED_EVENT } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { createBackupSeal, openBackup, parseBackup, readBackupFile, type PortableBackup, type VaultBackup } from "../vault/backup";
import { createVaultProfile, encryptSecret, unlockVault, type RecoveryPublicKey, type VaultProfile } from "../vault/crypto";
import type { VaultGrant } from "../vault/desktopVault";
import { readRecoveryQuestions, RecoveryQuestionFields } from "../vault/RecoveryQuestions";
import { useReauthStatus } from "../vault/useReauthStatus";
import { AppDialog } from "./AppDialog";
import { DialogFocusBoundary } from "./DialogFocusBoundary";

type BackupEntry = { filename: string; created_at: string; size: number; kind: "auto" | "manual" | "safety" };
type BackupPolicy = { interval_hours: number; retention: number; portable_ready: boolean };
type ProfileStatus = { initialized: boolean; profile: VaultProfile | null };
type NewProfile = VaultProfile & { questions?: ReturnType<typeof readRecoveryQuestions> };
type Operation =
  | { kind: "create" | "schedule" }
  | { kind: "file"; name: string; document: VaultBackup }
  | { kind: "restore" | "copy"; entry: BackupEntry };
type Prepared = {
  expected_digest: string | null;
  profile?: NewProfile;
  items: Awaited<ReturnType<typeof encryptSecret>>[];
  source_filename?: string;
  currentCount: number;
};

const policyPath = "/api/vault/backup-settings";
const filesPath = "/api/vault/backups";
const listKey = ["vault", "backups"];
const policyKey = ["vault", "backup-settings"];
const profileKey = ["vault", "profile"];
const intervalOptions = [[0, "禁用"], [6, "6 小时"], [12, "12 小时"], [24, "24 小时"], [48, "48 小时"], [168, "7 天"]] as const;
const retentionOptions = [3, 5, 10, 15, 20, 30, 50];
const labels = { auto: "自动备份", manual: "立即备份", safety: "恢复前安全备份" } as const;

function download(document: VaultBackup, filename: string) {
  const link = window.document.createElement("a");
  const url = URL.createObjectURL(new Blob([JSON.stringify(document)], { type: "application/json" }));
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function grantHeaders(token: string | null): HeadersInit | undefined {
  return token ? { "X-DBA-Vault-Token": token } : undefined;
}

function revoke(token: string) {
  void api("/api/vault/unlock?block_auto_unlock=false", { method: "DELETE", headers: grantHeaders(token), keepalive: true })
    .catch(() => undefined);
}

export function VaultBackupRestore({ desktop }: { desktop: boolean }) {
  const { session, reauthenticate } = useAuth();
  const { isCurrent } = useReauthStatus(session?.reauthenticated_until);
  const client = useQueryClient();
  const userId = session!.user!.id;
  const input = useRef<HTMLInputElement>(null);
  const review = useRef<HTMLParagraphElement>(null);
  const temporaryGrant = useRef<string | null>(null);
  const mounted = useRef(false);
  const contentId = useId();
  const heading = useId();
  const [operation, setOperation] = useState<Operation | null>(null);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [busy, setBusy] = useState(false);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [sectionError, setSectionError] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [notice, setNotice] = useState("");
  const files = useQuery({ queryKey: listKey, queryFn: () => api<BackupEntry[]>(filesPath), refetchInterval: 30_000 });
  const policy = useQuery({ queryKey: policyKey, queryFn: () => api<BackupPolicy>(policyPath) });
  const profile = useQuery({ queryKey: profileKey, queryFn: () => api<ProfileStatus>("/api/vault/profile") });
  const initialized = Boolean(profile.data?.profile);
  const userNeedsReauth = !desktop && !isCurrent();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (temporaryGrant.current) revoke(temporaryGrant.current);
    };
  }, []);
  useEffect(() => { if (prepared) review.current?.focus(); }, [prepared]);

  function releaseGrant() {
    if (!temporaryGrant.current) return;
    revoke(temporaryGrant.current);
    temporaryGrant.current = null;
  }

  function start(action: Operation) {
    setOperation(action); setPrepared(null); setDialogError(""); setSectionError(""); setNotice("");
  }

  function close() {
    if (busy) return;
    releaseGrant(); setPrepared(null); setOperation(null); setDialogError("");
  }

  async function changePolicy(key: "interval_hours" | "retention", value: number) {
    if (!policy.data) return;
    setPolicyBusy(true); setSectionError("");
    try {
      const updated = await api<BackupPolicy>(policyPath, { method: "PUT", body: jsonBody({ [key]: value }) });
      client.setQueryData(policyKey, updated);
    } catch (cause) { setSectionError(cause instanceof Error ? cause.message : "备份设置保存失败。"); }
    finally { setPolicyBusy(false); }
  }

  async function selectFile(file: File) {
    setSectionError(""); setNotice("");
    try { start({ kind: "file", name: file.name, document: await readBackupFile(file) }); }
    catch (cause) { setSectionError(cause instanceof Error ? cause.message : "无法打开备份文件。"); }
  }

  async function unlockCurrent(password: string, existing: VaultProfile) {
    try {
      return await unlockVault(password, userId, existing, desktop && !hasVaultAccessToken() ? async (wrappingKey) => {
        const grant = await api<VaultGrant>("/api/vault/unlock", { method: "POST", body: jsonBody({ wrapping_key: wrappingKey }) });
        if (!mounted.current) {
          revoke(grant.token);
          throw new Error("密码库备份窗口已关闭。");
        }
        temporaryGrant.current = grant.token;
      } : undefined);
    } catch (cause) {
      if (cause instanceof DOMException) throw new Error("当前密码库主密码不正确。");
      throw cause;
    }
  }

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!operation || busy) return;
    setBusy(true); setDialogError("");
    const form = new FormData(event.currentTarget);
    const read = (name: string) => String(form.get(name) ?? "");
    let dek: Uint8Array<ArrayBuffer> | undefined;
    try {
      const current = profile.data?.profile;
      if (userNeedsReauth) await reauthenticate(read("login_password"));
      if (operation.kind === "create" || operation.kind === "schedule") {
        const password = read("backup_password");
        if (password.length < 9 || password !== read("confirm_backup")) throw new Error("备份密码至少 9 位，两次输入必须一致。");
        if (!current) throw new Error("请先创建密码库。");
        dek = await unlockCurrent(read("master"), current);
        const credentials = { ...await createBackupSeal(password, userId, dek), recovery_wrapped_dek: current.recovery_wrapped_dek };
        const options = { method: "POST", body: jsonBody(credentials), headers: grantHeaders(temporaryGrant.current) };
        if (operation.kind === "create") {
          const result = await api<{ filename: string; document: PortableBackup }>(filesPath, options);
          download(result.document, result.filename);
          setNotice("已生成可用于换机的加密备份。");
        } else {
          client.setQueryData(policyKey, await api<BackupPolicy>(policyPath + "/password", options));
          setNotice("自动备份密码已保存。");
        }
        releaseGrant(); setOperation(null);
        void client.invalidateQueries({ queryKey: listKey });
        return;
      }

      const document = operation.kind === "file" ? operation.document : undefined;
      let records = document ? await openBackup(document, read("backup_password"), userId) : undefined;
      let newProfile: NewProfile | undefined;
      let snapshot: { digest: string; items: unknown[]; profile: VaultProfile } | undefined;
      if (current) {
        dek = await unlockCurrent(read("master"), current);
        const headers = grantHeaders(temporaryGrant.current);
        if (operation.kind === "restore" || operation.kind === "copy") {
          const saved = parseBackup(await api(filesPath + "/" + encodeURIComponent(operation.entry.filename), { headers }));
          if (operation.kind === "copy") {
            download(saved, operation.entry.filename);
            releaseGrant(); setOperation(null); setNotice("已生成备份文件副本。");
            return;
          }
          records = await openBackup(saved, read("backup_password"), userId);
        }
        snapshot = await api("/api/vault/backup", { headers });
        if (snapshot!.profile.wrapped_dek !== current.wrapped_dek) throw new Error("密码库已变更，请重新校验备份。");
      } else {
        if (operation.kind !== "file") throw new Error("请先创建密码库。");
        const password = read("master");
        if (password.length < 9 || password !== read("confirm_master")) throw new Error("新主密码至少 9 位，两次输入必须一致。");
        const recovery = await api<RecoveryPublicKey>("/api/vault/recovery-public-key");
        const created = await createVaultProfile(password, userId, recovery);
        newProfile = { ...created.profile, questions: desktop ? readRecoveryQuestions(form) : undefined };
        dek = created.dek;
      }
      if (!records) throw new Error("无法读取备份条目。");
      const items = await Promise.all(records.map((record) => encryptSecret(dek!, userId, record)));
      if (items.some((item) => item.ciphertext.length > 131072)) throw new Error("备份包含超出密码库支持长度的条目。");
      setPrepared({ expected_digest: snapshot?.digest ?? null, currentCount: snapshot?.items.length ?? 0,
        profile: newProfile, items, source_filename: operation.kind === "restore" ? operation.entry.filename : undefined });
    } catch (cause) {
      releaseGrant();
      setDialogError(cause instanceof Error ? cause.message : "无法校验密码库备份。");
    } finally { dek?.fill(0); setBusy(false); }
  }

  async function restore() {
    if (!prepared || busy) return;
    setBusy(true); setDialogError("");
    try {
      const { currentCount: _count, ...payload } = prepared;
      const result = await api<{ item_count: number; safety_backup: string | null }>("/api/vault/backup/restore", {
        method: "POST", body: jsonBody({ ...payload, confirm: "RESTORE" }), headers: grantHeaders(temporaryGrant.current),
      });
      temporaryGrant.current = null;
      window.dispatchEvent(new Event(VAULT_LOCKED_EVENT));
      setVaultAccessToken();
      setPrepared(null); setOperation(null);
      setNotice("已恢复 " + result.item_count + " 条。" + (result.safety_backup ? "覆盖前的安全备份已保存。" : ""));
      await client.invalidateQueries({ queryKey: ["vault"] });
    } catch (cause) { setDialogError(cause instanceof Error ? cause.message : "恢复失败。"); }
    finally { setBusy(false); }
  }

  const create = operation?.kind === "create";
  const schedule = operation?.kind === "schedule";
  const copy = operation?.kind === "copy";
  const name = operation?.kind === "file" ? operation.name
    : operation?.kind === "restore" || operation?.kind === "copy" ? operation.entry.filename : undefined;
  const canUseFile = Boolean(profile.data);
  return <section className="vault-backup-settings" aria-labelledby={contentId}>
    {policy.isError && <p role="alert" className="vault-backup-status">无法读取备份设置。<button type="button" className="button small" onClick={() => void policy.refetch()}>重试</button></p>}
    {policy.data && <>
      <div className="vault-backup-policy">
        <div>
          <label htmlFor={contentId + "-interval"}>自动备份间隔</label>
          <select id={contentId + "-interval"} value={policy.data.interval_hours} disabled={policyBusy} onChange={(event) => void changePolicy("interval_hours", Number(event.target.value))}>
            {intervalOptions.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={contentId + "-retention"}>备份保留数量</label>
          <select id={contentId + "-retention"} value={policy.data.retention} disabled={policyBusy} onChange={(event) => void changePolicy("retention", Number(event.target.value))}>
            {retentionOptions.map((value) => <option key={value} value={value}>{value} 个</option>)}
          </select>
        </div>
      </div>
      <div className="vault-backup-password">
        <div><strong>自动备份密码</strong><small>{policy.data.portable_ready ? "旧文件仍使用生成时的备份密码。" : "设置密码后，工作台运行时才会自动备份。"}</small></div>
        <button type="button" className="button small" disabled={!initialized} onClick={() => start({ kind: "schedule" })}>{policy.data.portable_ready ? "更改备份密码" : "设置备份密码"}</button>
      </div>
    </>}
    <div className="vault-backup-heading">
      <h4 id={contentId}>密码库备份</h4>
      <div className="button-row">
        <button type="button" className="button small" disabled={!initialized} onClick={() => start({ kind: "create" })}><Download aria-hidden="true" />立即备份</button>
        <button type="button" className="button small" disabled={!canUseFile} onClick={() => input.current?.click()}><Upload aria-hidden="true" />导入备份文件</button>
        <input ref={input} type="file" accept=".json,application/json" className="sr-only" tabIndex={-1} aria-label="选择密码库备份文件" onChange={(event) => {
          const selected = event.target.files?.[0]; event.target.value = "";
          if (selected) void selectFile(selected);
        }} />
      </div>
    </div>
    {profile.isError && <p role="alert" className="vault-backup-status">无法读取密码库状态。<button type="button" className="button small" onClick={() => void profile.refetch()}>重试</button></p>}
    {!initialized && profile.data && <p className="vault-backup-status">已有备份可以直接导入，恢复时会设置本机主密码。</p>}
    {notice && <p role="status" className="alert">{notice}</p>}
    {sectionError && <p role="alert" className="alert error">{sectionError}</p>}
    {files.isPending && <p role="status" className="vault-backup-status">正在读取备份列表…</p>}
    {files.isError && <p role="alert" className="vault-backup-status">无法读取备份列表。<button type="button" className="button small" onClick={() => void files.refetch()}>重试</button></p>}
    {files.data?.length === 0 && <p className="vault-backup-status">暂无密码库备份。</p>}
    {Boolean(files.data?.length) && <ul className="vault-backup-list" aria-label="密码库备份列表">
      {files.data!.map((entry) => <li className="vault-backup-entry" key={entry.filename}>
        <div className="vault-backup-file">
          <span title={entry.filename}>{entry.filename}</span>
          <small>{labels[entry.kind]} · {new Date(entry.created_at).toLocaleString()} · {Math.max(1, Math.round(entry.size / 1024))} KB</small>
        </div>
        <div className="button-row vault-backup-row-actions">
          <button type="button" className="button small" disabled={!initialized} onClick={() => start({ kind: "copy", entry })}><Download aria-hidden="true" />保存副本</button>
          <button type="button" className="button small" disabled={!initialized} onClick={() => start({ kind: "restore", entry })}><RotateCcw aria-hidden="true" />恢复</button>
        </div>
      </li>)}
    </ul>}
    {operation && <AppDialog className="modal vault-restore-dialog" labelledBy={heading} onClose={close}>
      <DialogFocusBoundary>
        <div className="modal-header"><h2 id={heading}>{create ? "立即备份" : schedule ? "设置自动备份密码" : copy ? "保存备份副本" : prepared ? "确认恢复密码库" : "校验密码库备份"}</h2>
          <button type="button" aria-label="关闭备份对话框" className="icon-button" onClick={close} disabled={busy}><X size={19} /></button></div>
        {name && <div className="backup-file"><strong title={name}>{name}</strong></div>}
        {prepared ? <>
          <p ref={review} tabIndex={-1}>备份已通过校验，包含 <strong>{prepared.items.length}</strong> 条凭据。</p>
          {prepared.expected_digest !== null && <div className="consequence-warning"><AlertTriangle size={19} aria-hidden="true" />
            <div><strong>恢复将替换本机密码库当前的 {prepared.currentCount} 条凭据。</strong><p>覆盖前会自动创建安全备份。</p></div>
          </div>}
          <div className="modal-actions"><button type="button" className="button" onClick={close} disabled={busy}>取消</button>
            {dialogError && <button type="button" className="button" onClick={() => { releaseGrant(); setPrepared(null); setDialogError(""); }} disabled={busy}>重新校验</button>}
            <button type="button" className="button primary" onClick={() => void restore()} disabled={busy}>{busy ? "正在恢复…" : "确认恢复"}</button></div>
        </> : <form className="stack" onSubmit={prepare}>
          {userNeedsReauth && <label>登录密码<input name="login_password" type="password" autoComplete="current-password" required disabled={busy} /></label>}
          {!copy && <label>备份密码<input name="backup_password" type="password" autoComplete={create || schedule ? "new-password" : "off"} minLength={9} maxLength={256} required disabled={busy} /></label>}
          {(create || schedule) && <label>确认备份密码<input name="confirm_backup" type="password" autoComplete="new-password" minLength={9} maxLength={256} required disabled={busy} /></label>}
          {operation.kind === "file" && operation.document.format === "dba-vault-backup-v1" && <p className="muted">旧版文件使用备份时的密码库主密码。</p>}
          {operation.kind === "restore" && operation.entry.kind === "safety" && <p className="muted">在设置自动备份密码前生成的安全备份，使用当时的密码库主密码。</p>}
          <label>{initialized ? "当前密码库主密码" : "设置本机密码库主密码"}<input name="master" type="password" autoComplete={initialized ? "current-password" : "new-password"} minLength={9} maxLength={256} required disabled={busy} /></label>
          {!initialized && <><label>确认本机主密码<input name="confirm_master" type="password" autoComplete="new-password" minLength={9} maxLength={256} required disabled={busy} /></label>
            {desktop && <fieldset disabled={busy}><RecoveryQuestionFields /></fieldset>}</>}
          <div className="modal-actions"><button type="button" className="button" onClick={close} disabled={busy}>取消</button>
            <button type="submit" className="button primary" disabled={busy}>{busy ? "处理中…" : create ? "生成备份" : schedule ? "保存密码" : copy ? "保存文件" : "校验备份"}</button></div>
        </form>}
        {dialogError && <p role="alert" className="alert error">{dialogError}</p>}
      </DialogFocusBoundary>
    </AppDialog>}
  </section>;
}
