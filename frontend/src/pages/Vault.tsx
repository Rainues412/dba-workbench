import { FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clipboard, Download, Eye, KeyRound, LockKeyhole, Pencil, Plus, Search, ShieldCheck, Star, Trash2, Upload, X } from "lucide-react";
import { ApiError, api, jsonBody, Page } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Pagination } from "../components/Pagination";
import {
  createVaultProfile, decryptSecret, encryptSecret, RecoveryPublicKey,
  unlockVault, VaultCipherItem, VaultProfile, VaultSecret,
} from "../vault/crypto";
import { startVaultAutoLock } from "../vault/autoLock";

const EMPTY_SECRET: VaultSecret = { site: "", url: "", username: "", password: "", category: "", notes: "", favorite: false };
const LEGACY_KEY = "wb_dba_workbench_accounts";

type ProfileResponse = { initialized: boolean; profile: VaultProfile | null };
type Decrypted = { cipher: VaultCipherItem; secret: VaultSecret };

async function loadAllItems(signal?: AbortSignal): Promise<VaultCipherItem[]> {
  const result: VaultCipherItem[] = [];
  for (let page = 1; ; page += 1) {
    const response = await api<Page<VaultCipherItem>>(`/api/vault/items?page=${page}&page_size=200`, { signal });
    result.push(...response.items);
    if (!response.has_next) return result;
  }
}

export function Vault() {
  const { session, reauthenticate } = useAuth();
  const client = useQueryClient();
  const [dek, setDek] = useState<Uint8Array<ArrayBuffer> | null>(null);
  const [secrets, setSecrets] = useState<Decrypted[]>([]);
  const [search, setSearch] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const panelRef = useRef<HTMLElement>(null);
  const paginationTop = useRef<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Decrypted | "new" | null>(null);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const dekRef = useRef(dek);
  dekRef.current = dek;
  const profile = useQuery({ queryKey: ["vault", "profile"], queryFn: () => api<ProfileResponse>("/api/vault/profile") });
  const legacyStatus = useQuery({
    queryKey: ["vault", "legacy"],
    queryFn: () => api<{ backend_entries: number; backend_key_available: boolean }>("/api/vault/legacy/status"),
  });
  const items = useQuery({
    queryKey: ["vault", "items"],
    queryFn: ({ signal }) => loadAllItems(signal),
    enabled: Boolean(dek),
  });
  const reauthenticated = Boolean(session?.reauthenticated_until && new Date(session.reauthenticated_until).getTime() > Date.now());
  const legacyLocal = readLegacyLocal();
  const filtered = useMemo(() => {
    const value = search.trim().toLocaleLowerCase();
    return secrets.filter(({ secret }) => (!favoritesOnly || secret.favorite) && (!value || [secret.site, secret.url, secret.username, secret.category, secret.notes].some((field) => field.toLocaleLowerCase().includes(value))));
  }, [search, secrets, favoritesOnly]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  useLayoutEffect(() => {
    if (paginationTop.current === null) return;
    const previousTop = paginationTop.current;
    paginationTop.current = null;
    const pagination = panelRef.current?.querySelector(".pagination");
    if (pagination) window.scrollBy({ top: pagination.getBoundingClientRect().top - previousTop, behavior: "instant" });
  }, [page]);

  function lock(message?: string) {
    dekRef.current?.fill(0);
    setDek(null); setSecrets([]); setRevealed(new Set()); setEditing(null); setPage(1);
    if (message) setNotice(message);
  }

  useEffect(() => () => { dekRef.current?.fill(0); }, []);
  useEffect(() => {
    if (!dek) return;
    return startVaultAutoLock((reason) => lock(reason === "idle" ? "保险箱已因闲置自动锁定" : "页面离开后保险箱已锁定"));
  }, [dek]);

  useEffect(() => {
    if (!dek || !items.data) return;
    let cancelled = false;
    Promise.all(items.data.map(async (cipher) => ({ cipher, secret: await decryptSecret(dek, cipher) })))
      .then((entries) => { if (!cancelled) setSecrets(entries); })
      .catch(() => { if (!cancelled) { setError("密文校验失败，保险箱已锁定"); lock(); } });
    return () => { cancelled = true; };
  }, [dek, items.data]);

  if (profile.isLoading) return <VaultPage><LoadingState label="读取保险箱状态" /></VaultPage>;
  if (profile.error) return <VaultPage><ErrorState message="保险箱状态加载失败" retry={() => void profile.refetch()} /></VaultPage>;

  async function verifyLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const formElement = event.currentTarget;
    const password = String(new FormData(formElement).get("login_password") ?? "");
    try { await reauthenticate(password); formElement.reset(); setNotice("敏感操作已授权 5 分钟"); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "登录密码验证失败"); }
  }

  async function initialize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const formElement = event.currentTarget;
    if (!reauthenticated) { setError("请先重新验证登录密码"); return; }
    const form = new FormData(formElement);
    const first = String(form.get("master_password") ?? "");
    if (first.length < 12 || first !== String(form.get("confirm_master") ?? "")) { setError("主密码至少 12 位，且两次输入必须一致"); return; }
    try {
      const recovery = await api<RecoveryPublicKey>("/api/vault/recovery-public-key");
      const created = await createVaultProfile(first, session!.user!.id, recovery);
      await api<VaultProfile>("/api/vault/profile", { method: "POST", body: jsonBody(created.profile) });
      setDek(created.dek); formElement.reset();
      await Promise.all([profile.refetch(), legacyStatus.refetch()]);
      await client.invalidateQueries({ queryKey: ["vault", "items"] });
      setNotice("保险箱已创建。请立即备份管理员恢复密钥并确认。 ");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保险箱创建失败"); }
  }

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const formElement = event.currentTarget;
    if (!reauthenticated) { setError("查看保险箱前请先重新验证登录密码"); return; }
    const password = String(new FormData(formElement).get("master_password") ?? "");
    try { const key = await unlockVault(password, session!.user!.id, profile.data!.profile!); setDek(key); formElement.reset(); setNotice("保险箱已解锁"); }
    catch { setError("主密码错误或密钥信封已损坏"); }
  }

  async function saveSecret(secret: VaultSecret, current?: Decrypted) {
    if (!dek || !reauthenticated) throw new Error("请先解锁并重新验证登录密码");
    const envelope = await encryptSecret(dek, session!.user!.id, secret, current?.cipher.item_key);
    if (current) {
      try {
        await api(`/api/vault/items/${current.cipher.id}`, { method: "PUT", body: jsonBody({ ...envelope, revision: current.cipher.revision }) });
      } catch (reason) {
        if (!(reason instanceof ApiError && reason.status === 409) || !window.confirm("该条目已在其他窗口修改。确定在最新版本上重新应用本次修改吗？")) throw reason;
        const latest = await loadAllItems();
        const latestItem = latest.find((item) => item.id === current.cipher.id);
        if (!latestItem) throw new Error("条目已被其他窗口删除");
        const retried = await encryptSecret(dek, session!.user!.id, secret, latestItem.item_key);
        await api(`/api/vault/items/${latestItem.id}`, { method: "PUT", body: jsonBody({ ...retried, revision: latestItem.revision }) });
      }
    } else await api("/api/vault/items", { method: "POST", body: jsonBody(envelope) });
    setEditing(null); await items.refetch(); setNotice(current ? "条目已更新" : "条目已创建");
  }

  async function remove(entry: Decrypted) {
    if (!reauthenticated) { setError("删除前请重新验证登录密码"); return; }
    if (!window.confirm(`确定删除“${entry.secret.site}”吗？`)) return;
    await api(`/api/vault/items/${entry.cipher.id}?revision=${entry.cipher.revision}`, { method: "DELETE" });
    await items.refetch(); setNotice("条目已删除");
  }

  async function copyPassword(entry: Decrypted) {
    if (!reauthenticated) { setError("复制前请重新验证登录密码"); return; }
    await navigator.clipboard.writeText(entry.secret.password);
    setNotice("密码已复制；系统会在 30 秒后尽力清空剪贴板");
    window.setTimeout(async () => {
      try { if (await navigator.clipboard.readText() === entry.secret.password) await navigator.clipboard.writeText(""); } catch { /* Browser permission can prevent best-effort clearing. */ }
    }, 30_000);
  }

  async function migrateLegacy() {
    if (!dek || !reauthenticated) { setError("迁移前请解锁并重新验证登录密码"); return; }
    setError("");
    try {
      const backend = await api<{ items: Array<Record<string, unknown>> }>("/api/vault/legacy/export", { method: "POST" });
      const combined = [
        ...legacyLocal.map((item, index) => ({ source: "local", key: `legacy_local_${String(item.id ?? index).padStart(8, "0")}`, item })),
        ...backend.items.map((item, index) => ({ source: "backend", key: `legacy_server_${String(item.legacy_id ?? index).padStart(8, "0")}`, item })),
      ];
      for (const entry of combined) {
        const secret = legacySecret(entry.item);
        const envelope = await encryptSecret(dek, session!.user!.id, secret, entry.key);
        try { await api("/api/vault/items", { method: "POST", body: jsonBody(envelope) }); }
        catch (reason) { if (!(reason instanceof ApiError && reason.status === 409)) throw reason; }
      }
      const migrated = new Map<string, VaultCipherItem>();
      let pageNumber = 1;
      do {
        const response = await api<Page<VaultCipherItem>>(`/api/vault/items?page=${pageNumber}&page_size=200`);
        response.items.forEach((item) => migrated.set(item.item_key, item));
        if (!response.has_next) break;
        pageNumber += 1;
      } while (true);
      for (const entry of combined) {
        const cipher = migrated.get(entry.key);
        if (!cipher || !sameSecret(await decryptSecret(dek, cipher), legacySecret(entry.item))) {
          throw new Error("迁移回读校验失败，旧数据已保留");
        }
      }
      await api("/api/vault/legacy/complete", { method: "POST", body: jsonBody({ expected_source_count: backend.items.length }) });
      if (legacyLocal.length) {
        localStorage.removeItem(LEGACY_KEY);
        localStorage.removeItem("wb_dba_workbench_pin");
      }
      await Promise.all([items.refetch(), legacyStatus.refetch()]); setNotice(`已迁移 ${combined.length} 条旧保险箱数据，源备份已保留`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "迁移失败，旧数据未清理"); }
  }

  async function downloadBackup() {
    if (!reauthenticated) { setError("备份前请重新验证登录密码"); return; }
    const backup = await api<Record<string, unknown>>("/api/vault/backup");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" }));
    link.download = `dba-vault-encrypted-${new Date().toISOString().slice(0, 10)}.json`;
    link.click(); URL.revokeObjectURL(link.href); setNotice("已生成只含密文的备份");
  }

  async function restoreBackup(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!reauthenticated) { setError("恢复前请重新验证登录密码"); return; }
    if (!window.confirm("恢复会替换当前保险箱密文。确定继续吗？")) return;
    try {
      const document = JSON.parse(await file.text()) as Record<string, unknown>;
      const result = await api<{ restored: boolean; item_count: number }>("/api/vault/backup/restore", {
        method: "POST", body: jsonBody({ ...document, confirm: "RESTORE" }),
      });
      lock(); await profile.refetch(); setNotice(`已恢复 ${result.item_count} 条密文；请重新解锁校验`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "备份恢复失败"); }
  }

  return <VaultPage>
    <header className="page-header"><div className="page-title-group"><span className="page-title-icon vault"><KeyRound size={24} /></span><div><p className="eyebrow">CLIENT-SIDE ENCRYPTED</p><h1>密码保险箱</h1><p className="muted">条目在浏览器内使用 Argon2id 与 AES-256-GCM 加解密。</p></div></div>{dek && <button className="button" onClick={() => lock("保险箱已锁定")}><LockKeyhole size={17} />立即锁定</button>}</header>
    {(notice || error) && <div className={`alert ${error ? "error" : ""}`} role={error ? "alert" : "status"}><span>{!error && <CheckCircle2 size={17} />}{error || notice}</span><button className="icon-button" onClick={() => { setError(""); setNotice(""); }} aria-label="关闭"><X size={17} /></button></div>}
    <section className="panel reauth-panel"><span className="reauth-icon"><ShieldCheck size={23} /></span><div><h2>敏感操作验证</h2><p className="muted">查看、复制、修改、删除、迁移和备份前，需要重新验证登录密码。</p></div><form onSubmit={verifyLogin}><input name="login_password" type="password" autoComplete="current-password" placeholder="登录密码" required /><button className="button">验证 5 分钟</button></form><span className={`badge ${reauthenticated ? "success" : "danger"}`}>{reauthenticated ? "已验证" : "未验证"}</span></section>
    {!profile.data!.initialized ? <section className="panel vault-gate"><span className="vault-gate-icon"><ShieldCheck size={30} /></span><h2>创建新保险箱</h2><p className="muted">保险箱主密码与登录密码分离。忘记后只能由本机管理员恢复。</p><form className="stack compact" onSubmit={initialize}><label>保险箱主密码<input name="master_password" type="password" minLength={12} autoComplete="new-password" required /></label><label>确认主密码<input name="confirm_master" type="password" minLength={12} autoComplete="new-password" required /></label><button className="button primary" disabled={!reauthenticated}><ShieldCheck size={17} />创建保险箱</button></form></section>
      : !dek ? <section className="panel vault-gate"><span className="vault-gate-icon"><LockKeyhole size={30} /></span><h2>保险箱已锁定</h2><p className="muted">刷新页面或离开页面后会保持锁定；闲置 5 分钟自动锁定。</p><form className="stack compact" onSubmit={unlock}><label>保险箱主密码<input name="master_password" type="password" autoComplete="current-password" required autoFocus /></label><button className="button primary" disabled={!reauthenticated}><LockKeyhole size={17} />解锁</button></form></section>
      : <>
        {!profile.data!.profile?.recovery_confirmed_at && <section className="panel recovery-callout"><span className="callout-icon"><Download size={22} /></span><div><h2>请备份管理员恢复密钥</h2><p className="muted">运行 <code>python -m backend.admin backup-recovery-key --output D:\Software\AI\Codex\dba-vault-recovery</code>，并将副本与数据库分开保存。</p></div><button className="button" onClick={async () => { await api("/api/vault/recovery/confirm", { method: "POST" }); await profile.refetch(); }}>我已完成备份</button></section>}
        <section className="panel data-panel" ref={panelRef}><div className="toolbar"><label className="search-field"><Search size={17} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="在全部已解锁条目中搜索" aria-label="搜索保险箱" /></label><label className="button"><input type="checkbox" checked={favoritesOnly} onChange={(event) => { setFavoritesOnly(event.target.checked); setPage(1); }} /><Star size={16} />仅收藏</label><div className="button-row"><button className="button" onClick={() => void downloadBackup()}><Download size={16} />加密备份</button><label className="button file-button"><Upload size={16} />恢复加密备份<input className="sr-only" type="file" accept="application/json,.json" onChange={(event) => void restoreBackup(event)} /></label><button className="button primary" onClick={() => reauthenticated ? setEditing("new") : setError("新增前请重新验证登录密码")}><Plus size={17} />新增条目</button></div></div>
          {(legacyLocal.length > 0 || (legacyStatus.data?.backend_entries ?? 0) > 0) && <div className="migration-banner"><span>检测到 {legacyLocal.length} 条浏览器旧数据和 {legacyStatus.data?.backend_entries ?? 0} 条后端旧数据。</span><button className="button" onClick={() => void migrateLegacy()}>迁移并校验</button></div>}
          {items.isLoading ? <LoadingState /> : items.error ? <ErrorState message="密文列表加载失败" retry={() => void items.refetch()} /> : !filtered.length ? <EmptyState title={search || favoritesOnly ? "没有匹配的条目" : "保险箱为空"} description={search || favoritesOnly ? "尝试调整搜索条件或取消收藏筛选。" : "新增条目，或迁移旧版保险箱数据。"} icon={ShieldCheck} /> : <div className="vault-grid">{visible.map((entry) => <article className="vault-card" key={entry.cipher.item_key}><div className="vault-card-heading"><span className="vault-item-icon"><KeyRound size={18} /></span><div><span className="badge">{entry.secret.category || "未分类"}</span>{entry.secret.favorite && <span className="badge"><Star size={13} />已收藏</span>}<h3>{entry.secret.site}</h3><p className="muted">{entry.secret.username || "未填写账号"}</p></div></div><div className="secret-row"><code>{revealed.has(entry.cipher.item_key) ? entry.secret.password : "••••••••••••"}</code><button className="button small" onClick={() => { if (!reauthenticated) return setError("查看前请重新验证登录密码"); setRevealed((current) => new Set(current).add(entry.cipher.item_key)); }}><Eye size={14} />查看</button><button className="button small" onClick={() => void copyPassword(entry)}><Clipboard size={14} />复制</button></div><div className="row-actions"><button className="button small" onClick={() => reauthenticated ? setEditing(entry) : setError("编辑前请重新验证登录密码")}><Pencil size={14} />编辑</button><button className="button small danger" onClick={() => void remove(entry)}><Trash2 size={14} />删除</button></div></article>)}</div>}
          {!items.isLoading && !items.error && <Pagination page={currentPage} pages={pages} total={filtered.length} pageSize={pageSize} onChange={(next) => { paginationTop.current = panelRef.current?.querySelector(".pagination")?.getBoundingClientRect().top ?? null; setPage(next); }} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />}
        </section>
      </>}
    {editing && <SecretEditor current={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSave={saveSecret} />}
  </VaultPage>;
}

function SecretEditor({ current, onClose, onSave }: { current?: Decrypted; onClose: () => void; onSave: (secret: VaultSecret, current?: Decrypted) => Promise<void> }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const value = current?.secret ?? EMPTY_SECRET;
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget); try { await onSave({ site: String(data.get("site") ?? ""), url: String(data.get("url") ?? ""), username: String(data.get("username") ?? ""), password: String(data.get("password") ?? ""), category: String(data.get("category") ?? ""), notes: String(data.get("notes") ?? ""), favorite: data.get("favorite") === "on" }, current); } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } finally { setBusy(false); } }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="secret-title"><div className="modal-header"><div><p className="eyebrow">SECURE RECORD</p><h2 id="secret-title">{current ? "编辑保险箱条目" : "新增保险箱条目"}</h2></div><button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button></div><form className="form-grid" onSubmit={submit}><label>系统/网站<input name="site" defaultValue={value.site} required autoFocus /></label><label>分类<input name="category" defaultValue={value.category} /></label><label className="full">网址<input name="url" type="url" defaultValue={value.url} /></label><label>账号<input name="username" defaultValue={value.username} /></label><label>密码<input name="password" type="password" defaultValue={value.password} required /></label><label className="full">备注<textarea name="notes" defaultValue={value.notes} rows={4} /></label><label className="full"><input type="checkbox" name="favorite" defaultChecked={value.favorite} />收藏此条目</label>{error && <div className="alert error full">{error}</div>}<div className="modal-actions full"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy}><CheckCircle2 size={17} />保存</button></div></form></section></div>;
}

function VaultPage({ children }: { children: React.ReactNode }) { return <div className="page vault-page">{children}</div>; }
function readLegacyLocal(): Array<Record<string, unknown>> { try { const value = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? "[]"); return Array.isArray(value) ? value : []; } catch { return []; } }
function legacySecret(item: Record<string, unknown>): VaultSecret { return { site: String(item.site ?? item.site_name ?? ""), url: String(item.url ?? item.site_url ?? ""), username: String(item.username ?? ""), password: String(item.password ?? ""), category: String(item.category ?? ""), notes: String(item.notes ?? ""), favorite: Boolean(item.favorite ?? item.is_favorite) }; }
function sameSecret(left: VaultSecret, right: VaultSecret): boolean { return left.site === right.site && left.url === right.url && left.username === right.username && left.password === right.password && left.category === right.category && left.notes === right.notes && left.favorite === right.favorite; }
