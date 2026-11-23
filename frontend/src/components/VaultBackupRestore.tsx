import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Download, FolderOpen, Pencil, RotateCcw, Trash2, Upload, X } from "lucide-react";
import { api, hasVaultAccessToken, jsonBody, setVaultAccessToken, VAULT_LOCKED_EVENT } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { openBackup, parseBackup, readBackupFile, readBackupIdentity, type VaultBackup } from "../vault/backup";
import { encryptSecret, unlockVault, type VaultProfile, type VaultSecret } from "../vault/crypto";
import type { VaultGrant } from "../vault/desktopVault";
import { useReauthStatus } from "../vault/useReauthStatus";
import { AppDialog } from "./AppDialog";
import { DialogFocusBoundary } from "./DialogFocusBoundary";
import { playTaskStatusFeedback, SubmitMorph, useTaskStatusReducedMotion, type TaskStatusPhase } from "./TaskStatusButton";
import { VaultImportProgress, VaultImportSteps, type VaultImportStep } from "./VaultImportProgress";

type BackupEntry = { filename: string; display_name?: string; created_at: string; size: number; kind: "auto" | "manual" | "safety" };
type BackupPolicy = { interval_hours: number; retention: number; directory: string; key_directory: string; portable_ready: boolean };
type ProfileStatus = { initialized: boolean; profile: VaultProfile | null };
type Operation =
  | { kind: "file" }
  | { kind: "restore" | "rename" | "delete"; entry: BackupEntry };
type Prepared = {
  expected_digest: string;
  items: Awaited<ReturnType<typeof encryptSecret>>[];
  currentCount: number;
  wrapping_key: string;
  preview: Pick<VaultSecret, "site" | "username" | "category">[];
};

const clearAuthorization = (authorization: { current: { dek: Uint8Array<ArrayBuffer> } | null }) => {
  authorization.current?.dek.fill(0);
  authorization.current = null;
};

const policyPath = "/api/vault/backup-settings";
const filesPath = "/api/vault/backups";
const listKey = ["vault", "backups"];
const policyKey = ["vault", "backup-settings"];
const profileKey = ["vault", "profile"];
const intervalOptions = [[0, "禁用"], [6, "6 小时"], [12, "12 小时"], [24, "24 小时"], [48, "48 小时"], [168, "7 天"]] as const;
const retentionOptions = [3, 5, 10, 15, 20, 30, 50];
const labels = { auto: "自动备份", manual: "手动备份", safety: "恢复前安全备份" } as const;

function grantHeaders(token: string | null): HeadersInit | undefined {
  return token ? { "X-DBA-Vault-Token": token } : undefined;
}

function revoke(token: string) {
  void api("/api/vault/unlock?block_auto_unlock=false", { method: "DELETE", headers: grantHeaders(token), keepalive: true })
    .catch(() => undefined);
}

function VerifyButton({ phase }: { phase?: TaskStatusPhase }) {
  return <SubmitMorph submit phase={phase} accessibleLabel="验证" feedback={phase === "pending" ? "正在验证…" : phase === "success" ? "主密码验证通过" : ""}>
    验证</SubmitMorph>;
}

export function VaultBackupRestore({ desktop, onOpenVault }: { desktop: boolean; onOpenVault?: () => void }) {
  const { session, reauthenticate } = useAuth();
  const { isCurrent } = useReauthStatus(session?.reauthenticated_until);
  const client = useQueryClient();
  const userId = session!.user!.id;
  const selection = useRef(0);
  const review = useRef<HTMLParagraphElement>(null);
  const stepFocus = useRef<HTMLInputElement>(null);
  const backupInput = useRef<HTMLInputElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);
  const temporaryGrant = useRef<string | null>(null);
  const mounted = useRef(false);
  const authorization = useRef<{ dek: Uint8Array<ArrayBuffer>; wrappingKey: string; envelope: string } | null>(null);
  const contentId = useId();
  const heading = useId();
  const [operation, setOperation] = useState<Operation | null>(null);
  const [selected, setSelected] = useState<{ name: string; path: string; document: VaultBackup } | null>(null);
  const [identityFile, setIdentityFile] = useState<{ file: File; path: string } | null>(null);
  const [submitPhase, setSubmitPhase] = useState<TaskStatusPhase>();
  const [importStep, setImportStep] = useState<VaultImportStep>(1);
  const [progressTarget, setProgressTarget] = useState(0);
  const [importComplete, setImportComplete] = useState(false);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [busy, setBusy] = useState(false);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [picking, setPicking] = useState(false);
  const [sectionError, setSectionError] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [notice, setNotice] = useState("");
  const [backupCreated, setBackupCreated] = useState(false);
  const files = useQuery({ queryKey: listKey, queryFn: () => api<BackupEntry[]>(filesPath), staleTime: 0, refetchInterval: 10_000 });
  const policy = useQuery({ queryKey: policyKey, queryFn: () => api<BackupPolicy>(policyPath), staleTime: 0 });
  const profile = useQuery({ queryKey: profileKey, queryFn: () => api<ProfileStatus>("/api/vault/profile") });
  const initialized = Boolean(profile.data?.profile);
  const userNeedsReauth = !desktop && !isCurrent();
  const reducedMotion = useTaskStatusReducedMotion();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearAuthorization(authorization);
      if (temporaryGrant.current) revoke(temporaryGrant.current);
    };
  }, []);
  useEffect(() => { if (prepared) review.current?.focus(); }, [prepared]);
  useEffect(() => { stepFocus.current?.focus(); }, [importStep]);
  useEffect(() => {
    if (!backupCreated) return;
    const timeout = window.setTimeout(() => setBackupCreated(false), 2000);
    return () => window.clearTimeout(timeout);
  }, [backupCreated]);

  function releaseGrant() {
    if (!temporaryGrant.current) return;
    revoke(temporaryGrant.current);
    temporaryGrant.current = null;
  }

  function start(action: Operation) {
    setSelected(null); setIdentityFile(null); setSubmitPhase(undefined);
    setImportStep(1); setProgressTarget(0); setImportComplete(false);
    setOperation(action); setPrepared(null); setDialogError(""); setSectionError(""); setNotice("");
  }

  function close() {
    if (busy || picking) return;
    selection.current++;
    clearAuthorization(authorization);
    releaseGrant(); setPrepared(null); setOperation(null); setDialogError("");
    setSelected(null); setIdentityFile(null);
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

  async function selectFile(file?: File, path = file?.name ?? "") {
    const id = ++selection.current;
    setSelected(null); setDialogError("");
    if (!file) return;
    try {
      const document = await readBackupFile(file);
      if (selection.current === id) {
        setSelected({ name: file.name, path, document });
        if (document.format !== "dba-vault-backup-v3") setIdentityFile(null);
      }
    } catch (cause) {
      if (selection.current === id) setDialogError(cause instanceof Error ? cause.message : "无法打开备份文件。");
    }
  }

  function selectIdentity(file?: File, path = file?.name ?? "") {
    setIdentityFile(file ? { file, path } : null);
    setDialogError("");
  }

  async function pickFile(kind: "backup" | "key") {
    if (!desktop) {
      (kind === "backup" ? backupInput : keyInput).current?.click();
      return;
    }
    setPicking(true); setDialogError("");
    try {
      const result = await api<{ name: string; path: string; text: string } | null>(`${filesPath}/pick-file?kind=${kind}`, {
        method: "POST", headers: grantHeaders(temporaryGrant.current),
      });
      if (!result || !mounted.current) return;
      const file = new File([result.text], result.name);
      if (kind === "backup") await selectFile(file, result.path);
      else selectIdentity(file, result.path);
    } catch (cause) { setDialogError(cause instanceof Error ? cause.message : "无法选择文件。"); }
    finally { setPicking(false); }
  }

  async function createBackup() {
    if (creating) return;
    setCreating(true); setSectionError(""); setNotice(""); setBackupCreated(false);
    try {
      await api(filesPath, { method: "POST" });
      setBackupCreated(true);
      void client.invalidateQueries({ queryKey: listKey });
    } catch (cause) { setSectionError(cause instanceof Error ? cause.message : "备份失败。"); }
    finally { setCreating(false); }
  }

  async function manageBackup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!operation || busy || (operation.kind !== "rename" && operation.kind !== "delete")) return;
    const path = `${filesPath}/${encodeURIComponent(operation.entry.filename)}`;
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    setBusy(true); setDialogError("");
    try {
      if (operation.kind === "rename") {
        await api(path, { method: "PATCH", body: jsonBody({ display_name: name }) });
        setNotice("备份名称已更新。");
      } else {
        const result = await api<{ replacement: string | null }>(path, { method: "DELETE" });
        setNotice(result.replacement ? "已删除并自动补建一份加密备份。" : "已删除备份。");
      }
      setOperation(null);
      void client.invalidateQueries({ queryKey: listKey });
    } catch (cause) { setDialogError(cause instanceof Error ? cause.message : "无法更新备份。"); }
    finally { setBusy(false); }
  }

  async function openDirectory(kind: "backup" | "key") {
    setSectionError("");
    try { await api(`${filesPath}/open-directory?kind=${kind}`, { method: "POST" }); }
    catch (cause) { setSectionError(cause instanceof Error ? cause.message : "无法打开目录。"); }
  }

  async function unlockCurrent(password: string, existing: VaultProfile, capture: (wrappingKey: string) => void) {
    try {
      return await unlockVault(password, userId, existing, async (wrappingKey) => {
        capture(wrappingKey);
        if (!desktop || hasVaultAccessToken()) return;
        const grant = await api<VaultGrant>("/api/vault/unlock", { method: "POST", body: jsonBody({ wrapping_key: wrappingKey }) });
        if (!mounted.current) {
          revoke(grant.token);
          throw new Error("密码库备份窗口已关闭。");
        }
        temporaryGrant.current = grant.token;
      });
    } catch (cause) {
      if (cause instanceof DOMException) throw new Error("当前密码库主密码不正确。");
      throw cause;
    }
  }

  async function verifyImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const current = profile.data?.profile;
    if (!current || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setDialogError(""); setSubmitPhase("pending");
    const verify = async () => {
      if (userNeedsReauth) await reauthenticate(String(form.get("login_password") ?? ""));
      let wrappingKey = "";
      const dek = await unlockCurrent(String(form.get("master") ?? ""), current, (key) => { wrappingKey = key; });
      try {
        await api("/api/vault/backup/verify-master", { method: "POST", body: jsonBody({ wrapping_key: wrappingKey }),
          headers: grantHeaders(temporaryGrant.current) });
        if (!mounted.current) return;
        authorization.current = { dek, wrappingKey, envelope: current.wrapped_dek };
      } finally { if (authorization.current?.dek !== dek) dek.fill(0); }
    };
    try {
      await playTaskStatusFeedback(verify(), reducedMotion, () => setSubmitPhase("success"));
      if (mounted.current) setImportStep(2);
    } catch (cause) {
      clearAuthorization(authorization); releaseGrant();
      setDialogError(cause instanceof Error ? cause.message : "主密码验证失败。");
    } finally { setBusy(false); setSubmitPhase(undefined); }
  }

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!operation || busy || picking || (operation.kind === "file" && !canImport)) return;
    setBusy(true); setDialogError("");
    const form = new FormData(event.currentTarget);
    const read = (name: string) => String(form.get(name) ?? "");
    let dek: Uint8Array<ArrayBuffer> | undefined;
    let wrappingKey = "";
    try {
      const current = profile.data?.profile;
      if (!current) throw new Error("请先前往保险箱设置主密码。");
      if (operation.kind !== "file" && userNeedsReauth) await reauthenticate(read("login_password"));
      let document = operation.kind === "file" ? selected?.document : undefined;
      let password = read("backup_password");
      if (operation.kind === "file") {
        if (!authorization.current || authorization.current.envelope !== current.wrapped_dek) {
          clearAuthorization(authorization); releaseGrant(); setImportStep(1);
          throw new Error("密码库已变更，请重新验证主密码。");
        }
        wrappingKey = authorization.current.wrappingKey;
      } else {
        dek = await unlockCurrent(read("master"), current, (key) => { wrappingKey = key; });
        const headers = grantHeaders(temporaryGrant.current);
        if (operation.kind === "restore") {
          document = parseBackup(await api(filesPath + "/" + encodeURIComponent(operation.entry.filename), { headers }));
        }
        if (document?.format === "dba-vault-backup-v3") {
          const { identity } = await api<{ identity: string }>("/api/vault/backup/key", {
            method: "POST", body: jsonBody({ wrapping_key: wrappingKey }), headers,
          });
          password = identity;
        }
      }
      const snapshot = await api<{ digest: string; items: unknown[]; profile: VaultProfile }>("/api/vault/backup", { headers: grantHeaders(temporaryGrant.current) });
      if (snapshot.profile.wrapped_dek !== current.wrapped_dek) throw new Error("密码库已变更，请重新校验备份。");
      if (!document) throw new Error("无法读取备份条目。");
      if (operation.kind === "file" && document.format === "dba-vault-backup-v3" && identityFile) {
        password = await readBackupIdentity(identityFile.file);
      }
      const records = await openBackup(document, password, userId);
      const targetDek = dek ?? authorization.current?.dek;
      if (!targetDek) throw new Error("请重新验证主密码。");
      const items = await Promise.all(records.map((record) => encryptSecret(targetDek, userId, record)));
      if (items.some((item) => item.ciphertext.length > 131072)) throw new Error("备份包含超出密码库支持长度的条目。");
      setPrepared({ expected_digest: snapshot.digest, currentCount: snapshot.items.length, items, wrapping_key: wrappingKey,
        preview: records.map(({ site, username, category }) => ({ site, username, category })) });
      clearAuthorization(authorization);
      if (operation.kind === "file") setImportStep(3);
    } catch (cause) {
      if (operation.kind !== "file") releaseGrant();
      setDialogError(cause instanceof Error ? cause.message : "无法校验密码库备份。");
    } finally { dek?.fill(0); setBusy(false); }
  }

  async function restore() {
    if (!prepared || busy) return;
    setBusy(true); setDialogError("");
    try {
      const { currentCount: _count, preview: _preview, ...payload } = prepared;
      if (operation?.kind === "file") setProgressTarget(35);
      const result = await api<{ item_count: number; safety_backup: string | null }>("/api/vault/backup/restore", {
        method: "POST", body: jsonBody({ ...payload, confirm: "RESTORE" }), headers: grantHeaders(temporaryGrant.current),
      });
      temporaryGrant.current = null;
      window.dispatchEvent(new Event(VAULT_LOCKED_EVENT));
      setVaultAccessToken();
      setNotice("已恢复 " + result.item_count + " 条。" + (result.safety_backup ? "覆盖前的安全备份已保存。" : ""));
      void client.invalidateQueries({ queryKey: ["vault"] });
      if (operation?.kind === "file") {
        setProgressTarget(100);
        return;
      }
      setPrepared(null); setOperation(null); setBusy(false);
    } catch (cause) {
      setProgressTarget(0); setBusy(false);
      setDialogError(cause instanceof Error ? cause.message : "恢复失败。");
    }
  }

  const finishImport = useCallback(() => setImportComplete(true), []);
  useEffect(() => {
    if (!importComplete) return;
    const timer = window.setTimeout(() => {
      setBusy(false); setOperation(null); setPrepared(null); setSelected(null); setIdentityFile(null);
    }, 460);
    return () => window.clearTimeout(timer);
  }, [importComplete]);

  const importing = operation?.kind === "file";
  const deleting = operation?.kind === "delete";
  const managing = operation?.kind === "rename" || deleting;
  const deletingLast = deleting && files.data?.length === 1 && Boolean(policy.data?.interval_hours);
  const legacyImport = Boolean(selected && selected.document.format !== "dba-vault-backup-v3");
  const canImport = Boolean(selected && (legacyImport || identityFile));
  const name = importing ? selected?.name : operation && "entry" in operation ? operation.entry.display_name ?? operation.entry.filename : undefined;
  const needsLegacyPassword = legacyImport || (operation?.kind === "restore" && operation.entry.filename.endsWith(".json"));
  const canUseFile = Boolean(profile.data);
  return <section className="vault-backup-settings" aria-labelledby={contentId}>
    <h4 id={contentId}>备份与恢复</h4>
    {policy.data && <div className="vault-backup-location">
      {([
        ["backup", "备份存放目录", "打开备份目录", policy.data.directory],
        ["key", "密钥存放目录", "打开密钥目录", policy.data.key_directory],
      ] as const).map(([kind, label, openLabel, path]) => <div className="vault-backup-location-item" key={kind} role="group" aria-labelledby={`${contentId}-${kind}-directory`}>
        <span id={`${contentId}-${kind}-directory`}>{label}</span>
        <div className="vault-path-row">
          <p className="vault-backup-directory" title={path}>{path}</p>
          <button type="button" className="button small" title={openLabel} aria-label={openLabel} onClick={() => void openDirectory(kind)}><FolderOpen aria-hidden="true" /></button>
        </div>
      </div>)}
    </div>}
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
      {initialized && !policy.data.portable_ready && <p className="vault-backup-status">下次正常解锁密码库时，工作台会自动准备备份密钥。</p>}
    </>}
    <div className="vault-backup-heading">
      <h5>密码库备份</h5>
      <div className="button-row">
        <button type="button" className="button small" disabled={!initialized || creating} onClick={() => void createBackup()}><Download aria-hidden="true" />手动备份</button>
        <button type="button" className="button small" disabled={!canUseFile} onClick={() => start({ kind: "file" })}><Upload aria-hidden="true" />导入</button>
      </div>
    </div>
    {profile.isError && <p role="alert" className="vault-backup-status">无法读取密码库状态。<button type="button" className="button small" onClick={() => void profile.refetch()}>重试</button></p>}
    {!initialized && profile.data && <p className="vault-backup-status">使用备份与恢复前，请先在保险箱设置主密码。</p>}
    {notice && <p role="status" className="alert">{notice}</p>}
    {backupCreated && createPortal(<div className="vault-backup-toast" role="status">
      <span className="vault-backup-toast-icon" aria-hidden="true"><Check size={10} strokeWidth={3} /></span>
      备份创建成功
    </div>, document.body)}
    {sectionError && <p role="alert" className="alert error">{sectionError}</p>}
    {files.isPending && <p role="status" className="vault-backup-status">正在读取备份列表…</p>}
    {files.isError && <p role="alert" className="vault-backup-status">无法读取备份列表。<button type="button" className="button small" onClick={() => void files.refetch()}>重试</button></p>}
    {files.data?.length === 0 && <p className="vault-backup-status">暂无密码库备份。</p>}
    {Boolean(files.data?.length) && <ul className="vault-backup-list" aria-label="密码库备份列表">
      {files.data!.map((entry) => <li className="vault-backup-entry" key={entry.filename}>
        <div className="vault-backup-file">
          <span title={entry.display_name ?? entry.filename}>{entry.display_name ?? entry.filename}</span>
          <small>{labels[entry.kind]} · {new Date(entry.created_at).toLocaleString()} · {Math.max(1, Math.round(entry.size / 1024))} KB</small>
        </div>
        <div className="button-row vault-backup-row-actions">
          <button type="button" className="button small" aria-label="重命名备份" title="重命名" onClick={() => start({ kind: "rename", entry })}><Pencil aria-hidden="true" /></button>
          <button type="button" className="button small vault-backup-delete" aria-label="删除备份" title="删除" onClick={() => start({ kind: "delete", entry })}><Trash2 aria-hidden="true" /></button>
          <button type="button" className="button small" disabled={!initialized} onClick={() => start({ kind: "restore", entry })}><RotateCcw aria-hidden="true" />恢复</button>
        </div>
      </li>)}
    </ul>}
    {operation && <AppDialog className={`modal vault-restore-dialog${deleting ? " vault-backup-delete-dialog" : ""}`}
      labelledBy={heading} describedBy={deleting ? `${heading}-description` : undefined} onClose={close}>
      <DialogFocusBoundary>
        <div className="modal-header"><div><h2 id={heading}>{importing ? "导入密码库备份" :
          operation.kind === "rename" ? "重命名备份" : deleting ? "删除备份" : prepared ? "确认恢复密码库" : "校验密码库备份"}</h2>
          {deleting && <p id={`${heading}-description`} className="vault-backup-delete-description">此备份将被永久删除，此操作无法撤消。</p>}</div>
          <button type="button" aria-label="关闭备份对话框" className="icon-button" onClick={close} disabled={busy || picking}><X size={19} /></button></div>
        {importing && initialized && <VaultImportSteps step={importStep} complete={importComplete} reduced={reducedMotion} />}
        {name && operation.kind !== "rename" && (!importing || prepared) && <div className="backup-file"><strong title={name}>{name}</strong></div>}
        {managing ? <form className="stack" onSubmit={manageBackup}>
          {operation.kind === "rename" && <label>备份名称<input name="name" defaultValue={name} maxLength={120} required disabled={busy} /></label>}
          {deletingLast && <p className="vault-backup-status">自动备份已开启，删除后会尝试补建一份新备份。</p>}
          <div className="modal-actions"><button type="submit" className={operation.kind === "rename" ? "button primary" : "button danger"} disabled={busy}>
            {operation.kind === "rename" ? "保存" : "确认删除"}</button></div>
        </form> : importing && !initialized ? <>
          <p>请先前往保险箱设置主密码，再返回导入备份。</p>
          <div className="modal-actions">
            {onOpenVault && <button type="button" className="button primary" onClick={() => { close(); onOpenVault(); }}>前往保险箱</button>}</div>
        </> : importing && importStep === 1 ? <form className="stack" onSubmit={verifyImport}>
          {userNeedsReauth && <label>登录密码<input name="login_password" type="password" autoComplete="current-password" required disabled={busy} /></label>}
          <label>当前密码库主密码<input ref={stepFocus} name="master" type="password" autoComplete="current-password" minLength={9} maxLength={256} required disabled={busy} /></label>
          <div className="modal-actions"><VerifyButton phase={submitPhase} /></div>
        </form> : prepared ? <>
          <p ref={review} tabIndex={-1}>备份已通过校验，包含 <strong>{prepared.items.length}</strong> 条凭据。</p>
          {importing && prepared.preview.length > 0 && <ul className="vault-import-preview" aria-label="将导入的密码条目" tabIndex={0}>
            {prepared.preview.map(({ site, username, category }, index) => <li key={index}>
              <strong title={site}>{site || "未命名条目"}</strong>
              {(username || category) && <small title={[username, category].filter(Boolean).join(" · ")}>{[username, category].filter(Boolean).join(" · ")}</small>}
            </li>)}
          </ul>}
          {prepared.currentCount > 0 && <div className="consequence-warning"><AlertTriangle size={19} aria-hidden="true" />
            <div><strong>恢复将替换本机密码库当前的 {prepared.currentCount} 条凭据。</strong><p>覆盖前会自动创建安全备份。</p></div>
          </div>}
          <div className="modal-actions">
            {dialogError && <button type="button" className="button" onClick={() => { releaseGrant(); start(operation); }} disabled={busy}>重新校验</button>}
            {importing ? busy ? <VaultImportProgress target={progressTarget} complete={importComplete} reduced={reducedMotion} onReachedEnd={finishImport} />
              : <button type="button" className="button primary" onClick={() => void restore()}>导入</button>
              : <button type="button" className="button primary" onClick={() => void restore()} disabled={busy}>{busy ? "正在恢复…" : "确认恢复"}</button>}</div>
        </> : <form className="stack" onSubmit={prepare}>
          {!importing && userNeedsReauth && <label>登录密码<input name="login_password" type="password" autoComplete="current-password" required disabled={busy} /></label>}
          {importing && <>
            <div className="vault-import-file-field">
              <label htmlFor={heading + "-backup"}>备份文件</label>
              <div className="vault-path-row">
                <input id={heading + "-backup"} ref={stepFocus} value={selected?.path ?? policy.data?.directory ?? ""}
                  title={selected?.path ?? policy.data?.directory} readOnly />
                <button type="button" className="button small" aria-label="浏览备份文件" title="浏览备份文件" disabled={busy || picking} onClick={() => void pickFile("backup")}><FolderOpen size={16} aria-hidden="true" /></button>
                <input ref={backupInput} hidden type="file" accept=".age,.json" aria-label="选择备份文件" disabled={busy}
                  onChange={(event) => { if (event.target.files?.[0]) void selectFile(event.target.files[0]); event.target.value = ""; }} />
              </div>
            </div>
            {!legacyImport && <div className="vault-import-file-field">
              <label htmlFor={heading + "-key"}>备份恢复密钥</label>
              <div className="vault-path-row">
                <input id={heading + "-key"} value={identityFile?.path ?? policy.data?.key_directory ?? ""}
                  title={identityFile?.path ?? policy.data?.key_directory} readOnly />
                <button type="button" className="button small" aria-label="浏览备份恢复密钥" title="浏览备份恢复密钥" disabled={busy || picking} onClick={() => void pickFile("key")}><FolderOpen size={16} aria-hidden="true" /></button>
                <input ref={keyInput} hidden type="file" accept=".txt,.key" aria-label="选择备份恢复密钥" disabled={busy}
                  onChange={(event) => { if (event.target.files?.[0]) selectIdentity(event.target.files[0]); event.target.value = ""; }} />
              </div>
            </div>}
          </>}
          {needsLegacyPassword && <label>旧版备份密码<input name="backup_password" type="password" autoComplete="off" minLength={9} maxLength={256} required disabled={busy} /></label>}
          {selected?.document.format === "dba-vault-backup-v1" && <p className="muted">此旧版文件使用备份时的密码库主密码。</p>}
          {!importing && <label>当前密码库主密码<input name="master" type="password" autoComplete="current-password" minLength={9} maxLength={256} required disabled={busy} /></label>}
          <div className="modal-actions">
            {importing ? <button type="submit" className="button primary" disabled={!canImport || busy || picking}>{busy ? "正在校验…" : "下一步"}</button>
              : <button type="submit" className="button primary" disabled={busy}>{busy ? "正在验证…" : "验证"}</button>}</div>
        </form>}
        {dialogError && <p role="alert" className="alert error">{dialogError}</p>}
      </DialogFocusBoundary>
    </AppDialog>}
  </section>;
}
