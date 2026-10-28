import { FormEvent, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clipboard, Download, Eye, EyeOff, Globe2, KeyRound, LockKeyhole, Pencil, Plus, RefreshCw, Search, ShieldCheck, Star, Tags, Trash2, Upload, UserRound, X } from "lucide-react";
import { ApiError, api, jsonBody, Page } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { Pagination } from "../components/Pagination";
import { EdgePasswordImport } from "../components/EdgePasswordImport";
import { VaultCategoryInput } from "../components/VaultCategoryInput";
import {
  createVaultProfile, decryptSecret, encryptSecret, RecoveryPublicKey,
  unlockVault, VaultCipherItem, VaultProfile, VaultSecret,
} from "../vault/crypto";
import { startVaultAutoLock } from "../vault/autoLock";
import { useReauthStatus } from "../vault/useReauthStatus";

const EMPTY_SECRET: VaultSecret = { site: "", url: "", username: "", password: "", category: "", notes: "", favorite: false };
const LEGACY_KEY = "wb_dba_workbench_accounts";
const NAME_COLLATOR = new Intl.Collator(["zh-CN", "en"], { numeric: true, sensitivity: "base" });

type ProfileResponse = { initialized: boolean; profile: VaultProfile | null };
type Decrypted = { cipher: VaultCipherItem; secret: VaultSecret };
type CaptchaChallenge = { challenge_id: string; image: string; expires_in: number };

async function loadAllItems(signal?: AbortSignal): Promise<VaultCipherItem[]> {
  const result: VaultCipherItem[] = [];
  for (let page = 1; ; page += 1) {
    const response = await api<Page<VaultCipherItem>>(`/api/vault/items?page=${page}&page_size=200`, { signal });
    result.push(...response.items);
    if (!response.has_next) return result;
  }
}

export function Vault() {
  const { session, reauthenticate, refreshError } = useAuth();
  const client = useQueryClient();
  const [dek, setDek] = useState<Uint8Array<ArrayBuffer> | null>(null);
  const [secrets, setSecrets] = useState<Decrypted[]>([]);
  const [search, setSearch] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const panelRef = useRef<HTMLElement>(null);
  const paginationTop = useRef<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Decrypted | "new" | null>(null);
  const [recoveringPassword, setRecoveringPassword] = useState(false);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [favoriting, setFavoriting] = useState<Set<string>>(new Set());
  const deletingRef = useRef(false);
  const favoritingRef = useRef(new Set<string>());
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
  const { reauthenticated, expired, remainingSeconds, isCurrent } = useReauthStatus(session?.reauthenticated_until);
  const reauthMinutes = session?.reauth_minutes ?? 30;
  const legacyLocal = readLegacyLocal();
  const categoryGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const { secret } of secrets) {
      const category = secret.category.trim();
      counts.set(category, (counts.get(category) ?? 0) + 1);
    }
    return [...counts].sort(([left], [right]) => left ? right ? NAME_COLLATOR.compare(left, right) : -1 : right ? 1 : 0);
  }, [secrets]);
  const filtered = useMemo(() => {
    const value = search.trim().toLocaleLowerCase();
    return secrets
      .filter(({ secret }) => (categoryFilter === null || secret.category.trim() === categoryFilter) && (!favoritesOnly || secret.favorite) && (!value || secret.site.toLocaleLowerCase().includes(value)))
      .sort((left, right) => Number(right.secret.favorite) - Number(left.secret.favorite) || NAME_COLLATOR.compare(left.secret.site.trim(), right.secret.site.trim()) || NAME_COLLATOR.compare(left.secret.url, right.secret.url) || NAME_COLLATOR.compare(left.secret.username, right.secret.username) || left.cipher.id - right.cipher.id);
  }, [categoryFilter, search, secrets, favoritesOnly]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const visibleSelectedCount = visible.filter((entry) => selected.has(entry.cipher.item_key)).length;
  const allVisibleSelected = visible.length > 0 && visibleSelectedCount === visible.length;
  const someVisibleSelected = visibleSelectedCount > 0 && !allVisibleSelected;

  useLayoutEffect(() => {
    if (paginationTop.current === null) return;
    const previousTop = paginationTop.current;
    paginationTop.current = null;
    const pagination = panelRef.current?.querySelector(".pagination");
    if (pagination) window.scrollBy({ top: pagination.getBoundingClientRect().top - previousTop, behavior: "instant" });
  }, [page]);

  function lock(message?: string) {
    dekRef.current?.fill(0);
    dekRef.current = null;
    setDek(null); setSecrets([]); setRevealed(new Set()); setSelected(new Set()); setEditing(null); setCategoryFilter(null); setPage(1);
    if (message) setNotice(message);
  }

  useEffect(() => () => { dekRef.current?.fill(0); dekRef.current = null; }, []);
  useEffect(() => { setSelected(new Set()); setRevealed(new Set()); }, [page, pageSize, search, favoritesOnly, categoryFilter]);
  useEffect(() => { if (!reauthenticated) setRevealed(new Set()); }, [reauthenticated]);
  useEffect(() => {
    if (expired) setNotice((current) => current.startsWith("敏感操作已授权") ? "" : current);
  }, [expired]);
  useEffect(() => {
    if (!dek) return;
    return startVaultAutoLock(() => lock("保险箱已因闲置自动锁定"));
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
  if (profile.error && !profile.data) return <VaultPage><ErrorState message="保险箱状态加载失败" retry={() => void profile.refetch()} /></VaultPage>;

  async function verifyLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const formElement = event.currentTarget;
    const password = String(new FormData(formElement).get("login_password") ?? "");
    try { await reauthenticate(password); formElement.reset(); setNotice(`敏感操作已授权 ${reauthMinutes} 分钟`); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "登录密码验证失败"); }
  }

  async function initialize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const formElement = event.currentTarget;
    if (!isCurrent()) { setError("请先重新验证登录密码"); return; }
    const form = new FormData(formElement);
    const first = String(form.get("master_password") ?? "");
    if (first.length < 9 || first !== String(form.get("confirm_master") ?? "")) { setError("主密码至少 9 位，且两次输入必须一致"); return; }
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
    if (!isCurrent()) { setError("查看保险箱前请先重新验证登录密码"); return; }
    const password = String(new FormData(formElement).get("master_password") ?? "");
    try { const key = await unlockVault(password, session!.user!.id, profile.data!.profile!); setDek(key); formElement.reset(); setNotice("保险箱已解锁"); }
    catch { setError("主密码错误或密钥信封已损坏"); }
  }

  async function saveSecret(secret: VaultSecret, current?: Decrypted) {
    if (!dek || !isCurrent()) throw new Error("请先解锁并重新验证登录密码");
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
    await removeEntries([entry]);
  }

  async function removeEntries(entries: Decrypted[]) {
    if (!entries.length || deletingRef.current) return;
    const key = dekRef.current;
    const authorized = () => key && dekRef.current === key && Boolean(session?.reauthenticated_until && new Date(session.reauthenticated_until).getTime() > Date.now());
    if (!authorized()) { setError("删除前请解锁并重新验证登录密码"); return; }
    if (!window.confirm(`确定永久删除选中的 ${entries.length} 条密码吗？此操作不可撤销，请先确认已有加密备份。`)) return;
    deletingRef.current = true; setDeleting(true); setError(""); setNotice("");
    let removed = 0;
    try {
      for (const entry of entries) {
        if (!authorized()) throw new Error("授权已失效");
        await api(`/api/vault/items/${entry.cipher.id}?revision=${entry.cipher.revision}`, { method: "DELETE" });
        removed += 1;
        setSecrets((current) => current.filter((item) => item.cipher.item_key !== entry.cipher.item_key));
        setSelected((current) => { const next = new Set(current); next.delete(entry.cipher.item_key); return next; });
        setRevealed((current) => { const next = new Set(current); next.delete(entry.cipher.item_key); return next; });
      }
      setNotice(`已删除 ${removed} 条密码`);
    } catch {
      setError(`删除已暂停：已删除 ${removed} 条，剩余 ${entries.length - removed} 条未确认删除。请刷新核对；若条目已被修改，不会强制删除。`);
    } finally {
      deletingRef.current = false; setDeleting(false);
      await items.refetch();
    }
  }

  function togglePassword(entry: Decrypted) {
    const itemKey = entry.cipher.item_key;
    // Hiding remains available even after the sensitive-operation grant expires.
    if (!revealed.has(itemKey) && !(session?.reauthenticated_until && new Date(session.reauthenticated_until).getTime() > Date.now())) {
      setError("查看前请重新验证登录密码"); return;
    }
    setRevealed((current) => { const next = new Set(current); if (next.has(itemKey)) next.delete(itemKey); else next.add(itemKey); return next; });
  }

  async function toggleFavorite(entry: Decrypted) {
    const itemKey = entry.cipher.item_key;
    if (favoritingRef.current.has(itemKey)) return;
    if (!isCurrent()) { setError("收藏前请重新验证登录密码"); return; }
    favoritingRef.current.add(itemKey);
    setFavoriting((current) => new Set(current).add(itemKey));
    setError("");
    try {
      await saveSecret({ ...entry.secret, favorite: !entry.secret.favorite }, entry);
      setNotice(entry.secret.favorite ? "已取消收藏" : "已收藏");
    } catch {
      setError("收藏状态更新失败；若条目已在其他窗口修改，请刷新后重试");
    } finally {
      favoritingRef.current.delete(itemKey);
      setFavoriting((current) => { const next = new Set(current); next.delete(itemKey); return next; });
    }
  }

  async function copyPassword(entry: Decrypted) {
    if (!isCurrent()) { setError("复制前请重新验证登录密码"); return; }
    await navigator.clipboard.writeText(entry.secret.password);
    setNotice("密码已复制；系统会在 30 秒后尽力清空剪贴板");
    window.setTimeout(async () => {
      try { if (await navigator.clipboard.readText() === entry.secret.password) await navigator.clipboard.writeText(""); } catch { /* Browser permission can prevent best-effort clearing. */ }
    }, 30_000);
  }

  async function migrateLegacy() {
    if (!dek || !isCurrent()) { setError("迁移前请解锁并重新验证登录密码"); return; }
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
    if (!isCurrent()) { setError("备份前请重新验证登录密码"); return; }
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
    if (!isCurrent()) { setError("恢复前请重新验证登录密码"); return; }
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
    <section className="panel reauth-panel"><span className="reauth-icon"><ShieldCheck size={23} /></span><div><h2>敏感操作验证</h2><p className="muted">查看、复制、修改、删除、迁移和备份前，需要重新验证登录密码。</p></div><form onSubmit={verifyLogin}><input name="login_password" type="password" minLength={9} autoComplete="current-password" placeholder="登录密码" required /><button className="button">验证 {reauthMinutes} 分钟</button></form><div className="reauth-state"><span className={`badge ${reauthenticated ? "success" : "danger"}`}><span>{reauthenticated ? "已验证" : expired ? "已过期" : "未验证"}</span></span>{reauthenticated && <span className="reauth-countdown" aria-label="验证剩余时间">剩余 {Math.floor(remainingSeconds / 60).toString().padStart(2, "0")}:{(remainingSeconds % 60).toString().padStart(2, "0")}</span>}</div></section>
    {expired && <div className="alert error" role="status">敏感操作验证已过期，请重新输入登录密码验证。</div>}
    {refreshError && <div className="alert error" role="status">登录状态暂未同步，恢复连接后会自动重试。</div>}
    {profile.error && <div className="alert error" role="status">保险箱状态暂未同步，恢复连接后会自动重试。</div>}
    {!profile.data!.initialized ? <section className="panel vault-gate"><span className="vault-gate-icon"><ShieldCheck size={30} /></span><h2>创建新保险箱</h2><p className="muted">保险箱主密码与登录密码分离。忘记后只能由本机管理员恢复。</p><form className="stack compact" onSubmit={initialize}><label>保险箱主密码<input name="master_password" type="password" minLength={9} autoComplete="new-password" required /></label><label>确认主密码<input name="confirm_master" type="password" minLength={9} autoComplete="new-password" required /></label><button className="button primary" disabled={!reauthenticated}><ShieldCheck size={17} />创建保险箱</button></form></section>
      : !dek ? <section className="panel vault-gate"><span className="vault-gate-icon"><LockKeyhole size={30} /></span><h2>保险箱已锁定</h2><form className="stack compact vault-unlock-form" onSubmit={unlock}><label>保险箱主密码<input name="master_password" type="password" minLength={9} autoComplete="current-password" required autoFocus /></label><button type="button" className="vault-forgot-link" onClick={() => setRecoveringPassword(true)}>忘记密码</button><button className="button primary" disabled={!reauthenticated}><LockKeyhole size={17} />解锁</button></form><p className="vault-lock-hint"><ShieldCheck size={14} aria-hidden="true" /><span><span className="vault-lock-hint-part">刷新页面后需重新解锁；</span><span className="vault-lock-hint-part">连续 15 分钟无操作将自动锁定。</span></span></p></section>
      : <>
        <div className="button-row"><EdgePasswordImport dek={dek} userId={session!.user!.id} canImport={() => dekRef.current === dek && Boolean(session?.reauthenticated_until && new Date(session.reauthenticated_until).getTime() > Date.now())} loadExisting={async () => { const key = dekRef.current; if (!key) throw new Error("保险箱已锁定"); return Promise.all((await loadAllItems()).map((item) => decryptSecret(key, item))); }} onImported={async () => { await items.refetch(); }} /></div>
        {!profile.data!.profile?.recovery_confirmed_at && <section className="panel recovery-callout"><span className="callout-icon"><Download size={22} /></span><div><h2>请备份管理员恢复密钥</h2><p className="muted">在 server 目录运行 <code>python -m backend.admin backup-recovery-key --output &lt;绝对备份目录&gt;</code>，并将副本与数据库分开保存。</p></div><button className="button" onClick={async () => { await api("/api/vault/recovery/confirm", { method: "POST" }); await profile.refetch(); }}>我已完成备份</button></section>}
        <section className="panel data-panel" ref={panelRef}><div className="toolbar"><label className="search-field"><Search size={17} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="按名称搜索已解锁条目" aria-label="按名称搜索保险箱" /></label><button className={`button vault-filter-toggle${favoritesOnly ? " is-active" : ""}`} aria-pressed={favoritesOnly} onClick={() => { setFavoritesOnly((current) => !current); setPage(1); }}><Star size={16} fill={favoritesOnly ? "currentColor" : "none"} />仅看收藏</button><div className="button-row"><button className="button" onClick={() => void downloadBackup()}><Download size={16} />加密备份</button><label className="button file-button"><Upload size={16} />恢复加密备份<input className="sr-only" type="file" accept="application/json,.json" onChange={(event) => void restoreBackup(event)} /></label><button className="button primary" onClick={() => isCurrent() ? setEditing("new") : setError("新增前请重新验证登录密码")}><Plus size={17} />新增条目</button></div></div>
          {(legacyLocal.length > 0 || (legacyStatus.data?.backend_entries ?? 0) > 0) && <div className="migration-banner"><span>检测到 {legacyLocal.length} 条浏览器旧数据和 {legacyStatus.data?.backend_entries ?? 0} 条后端旧数据。</span><button className="button" onClick={() => void migrateLegacy()}>迁移并校验</button></div>}
          {!items.isLoading && !items.error && secrets.length > 0 && <div className="vault-category-groups" role="group" aria-label="保险箱分类分组">
            <span className="vault-category-title"><Tags size={15} />分类分组</span>
            <div className="vault-category-options">
              <button className="vault-category-button" aria-label={`全部分类，${secrets.length} 条`} aria-pressed={categoryFilter === null} onClick={() => { setCategoryFilter(null); setPage(1); }}><span className="vault-category-name">全部</span><span className="vault-category-count">{secrets.length}</span></button>
              {categoryGroups.map(([category, count]) => <button className="vault-category-button" aria-label={`${category || "未分类"}，${count} 条`} aria-pressed={categoryFilter === category} title={category || "未分类"} key={category || "__uncategorized__"} onClick={() => { setCategoryFilter(category); setPage(1); }}><span className="vault-category-name">{category || "未分类"}</span><span className="vault-category-count">{count}</span></button>)}
            </div>
          </div>}
          {!items.isLoading && !items.error && visible.length > 0 && <div className="vault-selection">
            <label className={`checkbox-label vault-choice vault-select-all${allVisibleSelected ? " is-all-selected" : someVisibleSelected ? " has-selection" : ""}`}><input type="checkbox" aria-label="全选当前页" disabled={deleting} checked={allVisibleSelected} ref={(input) => { if (input) input.indeterminate = someVisibleSelected; }} onChange={(event) => setSelected(event.target.checked ? new Set(visible.map((entry) => entry.cipher.item_key)) : new Set())} /><span>{allVisibleSelected ? `本页已全选 ${visible.length} 条` : someVisibleSelected ? `已选 ${visibleSelectedCount} / ${visible.length} 条` : `全选当前页 ${visible.length} 条`}</span></label>
            <button className="button small" disabled={deleting || !selected.size} onClick={() => setSelected(new Set())}>取消选择</button>
            <button className="button small danger" disabled={deleting || !selected.size} onClick={() => void removeEntries(visible.filter((entry) => selected.has(entry.cipher.item_key)))}><Trash2 size={14} />{deleting ? "正在删除…" : "删除所选"}</button>
          </div>}
          {items.isLoading ? <LoadingState /> : items.error ? <ErrorState message="密文列表加载失败" retry={() => void items.refetch()} /> : !filtered.length ? <EmptyState title={search || favoritesOnly || categoryFilter !== null ? "没有匹配的条目" : "保险箱为空"} description={search || favoritesOnly || categoryFilter !== null ? "尝试调整搜索、收藏或分类筛选。" : "新增条目，或迁移旧版保险箱数据。"} icon={ShieldCheck} /> : <div className="vault-grid">{visible.map((entry) => {
            const isRevealed = revealed.has(entry.cipher.item_key);
            const isSelected = selected.has(entry.cipher.item_key);
            return <article className={`vault-card${isSelected ? " is-selected" : ""}`} key={entry.cipher.item_key}>
              <div className="vault-card-top">
                <label className="vault-select"><input type="checkbox" aria-label={`选择 ${entry.secret.site}`} disabled={deleting} checked={isSelected} onChange={(event) => { const checked = event.target.checked; setSelected((current) => { const next = new Set(current); if (checked) next.add(entry.cipher.item_key); else next.delete(entry.cipher.item_key); return next; }); }} /></label>
                <div className="vault-card-badges"><button className={`icon-button vault-favorite-action${entry.secret.favorite ? " is-active" : ""}`} disabled={favoriting.has(entry.cipher.item_key)} aria-pressed={entry.secret.favorite} aria-label={`${entry.secret.favorite ? "取消收藏" : "收藏"} ${entry.secret.site}`} title={entry.secret.favorite ? "取消收藏" : "收藏"} onClick={() => void toggleFavorite(entry)}><Star size={17} fill={entry.secret.favorite ? "currentColor" : "none"} /></button><span className="badge">{entry.secret.category || "未分类"}</span></div>
              </div>
              <div className="vault-card-heading"><span className="vault-item-icon"><KeyRound size={18} /></span><div><h3>{entry.secret.site}</h3></div></div>
              <dl className="vault-card-details">
                <div><dt><Globe2 size={14} />网址</dt><dd>{entry.secret.url || "未填写网址"}</dd></div>
                <div><dt><UserRound size={14} />账号名</dt><dd>{entry.secret.username || "未填写账号"}</dd></div>
              </dl>
              <div className="secret-row"><div className="secret-value"><span className="vault-field-label">密码</span><code>{isRevealed ? entry.secret.password : "••••••••••••"}</code></div><div className="secret-actions"><button className="button small" aria-pressed={isRevealed} onClick={() => togglePassword(entry)}>{isRevealed ? <EyeOff size={14} /> : <Eye size={14} />}{isRevealed ? "隐藏" : "查看"}</button><button className="button small" onClick={() => void copyPassword(entry)}><Clipboard size={14} />复制</button></div></div>
              <div className="row-actions"><button className="button small" disabled={deleting} onClick={() => isCurrent() ? setEditing(entry) : setError("编辑前请重新验证登录密码")}><Pencil size={14} />编辑</button><button className="button small danger" disabled={deleting} onClick={() => void remove(entry)}><Trash2 size={14} />删除</button></div>
            </article>;
          })}</div>}
          {!items.isLoading && !items.error && <Pagination page={currentPage} pages={pages} total={filtered.length} pageSize={pageSize} onChange={(next) => { paginationTop.current = panelRef.current?.querySelector(".pagination")?.getBoundingClientRect().top ?? null; setPage(next); }} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />}
        </section>
      </>}
    {editing && <SecretEditor authorized={reauthenticated} categories={categoryGroups.map(([category]) => category).filter(Boolean)} current={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSave={saveSecret} />}
    {recoveringPassword && !dek && <ForgotMasterPasswordEditor onClose={() => setRecoveringPassword(false)} onChanged={async () => { await profile.refetch(); setNotice("保险箱主密码已重置，请使用新密码解锁"); setRecoveringPassword(false); }} />}
  </VaultPage>;
}

function ForgotMasterPasswordEditor({ onClose, onChanged }: { onClose: () => void; onChanged: () => Promise<void> }) {
  const [captcha, setCaptcha] = useState<CaptchaChallenge | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function refreshCaptcha() {
    try { setCaptcha(await api<CaptchaChallenge>("/api/vault/captcha")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "验证码加载失败"); }
  }
  useEffect(() => { void refreshCaptcha(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = String(form.get("new_master_password") ?? "");
    if (next.length < 9 || next !== String(form.get("confirm_master_password") ?? "")) { setError("新主密码至少 9 位，且两次输入必须一致"); return; }
    if (!captcha) { setError("请先获取验证码"); return; }
    setBusy(true); setError("");
    try {
      await api("/api/vault/profile/recover", { method: "PUT", body: jsonBody({
        new_master_password: next,
        login_password: String(form.get("login_password") ?? ""),
        captcha_id: captcha.challenge_id,
        captcha_code: String(form.get("captcha_code") ?? ""),
      }) });
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "主密码重置失败");
      await refreshCaptcha();
    } finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="modal vault-password-modal" role="dialog" aria-modal="true" aria-labelledby="vault-password-title"><div className="modal-header"><div><p className="eyebrow">RECOVERY</p><h2 id="vault-password-title">重置保险箱主密码</h2></div><button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button></div><p className="muted">验证登录密码与本机验证码后，系统会使用管理员恢复密钥重新保护数据密钥；密码条目不会被逐条解密或重写。</p><form className="form-grid" onSubmit={submit}><label className="full">登录密码<input name="login_password" type="password" minLength={9} autoComplete="current-password" required autoFocus /></label><label>新保险箱主密码<input name="new_master_password" type="password" minLength={9} autoComplete="new-password" required /></label><label>确认新主密码<input name="confirm_master_password" type="password" minLength={9} autoComplete="new-password" required /></label><label className="full">验证码<div className="captcha-row">{captcha ? <img src={captcha.image} alt="本机验证码" /> : <span className="captcha-placeholder">正在生成…</span>}<input name="captcha_code" minLength={5} maxLength={5} autoComplete="off" placeholder="输入 5 位验证码" required /><button type="button" className="icon-button" onClick={() => void refreshCaptcha()} aria-label="刷新验证码" title="刷新验证码"><RefreshCw size={17} /></button></div></label>{error && <div className="alert error full" role="alert">{error}</div>}<div className="modal-actions full"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy || !captcha}><KeyRound size={17} />{busy ? "正在重置…" : "确认重置"}</button></div></form></section></div>;
}

function SecretEditor({ current, categories, authorized, onClose, onSave }: { current?: Decrypted; categories: string[]; authorized: boolean; onClose: () => void; onSave: (secret: VaultSecret, current?: Decrypted) => Promise<void> }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const value = current?.secret ?? EMPTY_SECRET;
  const [showPassword, setShowPassword] = useState(false);
  const passwordId = useId();
  const { reauthenticate, session } = useAuth();
  const [reauthPassword, setReauthPassword] = useState("");
  useEffect(() => { if (!authorized) setShowPassword(false); else setReauthPassword(""); }, [authorized]);
  async function renewAuthorization() {
    setBusy(true); setError("");
    try { await reauthenticate(reauthPassword); setReauthPassword(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "登录密码验证失败"); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget); try { await onSave({ site: String(data.get("site") ?? ""), url: String(data.get("url") ?? ""), username: String(data.get("vault_entry_username") ?? ""), password: String(data.get("vault_entry_password") ?? ""), category: String(data.get("category") ?? ""), notes: String(data.get("notes") ?? ""), favorite: data.get("favorite") === "on" }, current); } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } finally { setBusy(false); } }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="secret-title"><div className="modal-header"><div><p className="eyebrow">SECURE RECORD</p><h2 id="secret-title">{current ? "编辑保险箱条目" : "新增保险箱条目"}</h2></div><button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button></div><form className="form-grid" autoComplete="off" onSubmit={submit}><label>名称或备注<input name="site" defaultValue={value.site} required autoFocus /></label><VaultCategoryInput categories={categories} initialValue={value.category} /><label className="full">网址<input name="url" type="url" defaultValue={value.url} /></label><label>账号名<input name="vault_entry_username" autoComplete="off" autoCapitalize="none" defaultValue={value.username} /></label><div className="vault-password-field"><label htmlFor={passwordId}>密码</label><div className="vault-password-input"><input id={passwordId} name="vault_entry_password" autoComplete="new-password" autoCapitalize="none" type={showPassword ? "text" : "password"} defaultValue={value.password} spellCheck={false} required /><button type="button" className="icon-button" disabled={!authorized} aria-label={showPassword ? "隐藏密码" : "显示密码"} title={showPassword ? "隐藏密码" : "显示密码"} aria-pressed={showPassword} aria-controls={passwordId} onMouseDown={(event) => event.preventDefault()} onClick={() => { if (showPassword || (session?.reauthenticated_until && Date.parse(session.reauthenticated_until) > Date.now())) setShowPassword((visible) => !visible); }}>{showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button></div></div><label className="full">详细备注<textarea name="notes" defaultValue={value.notes} rows={4} /></label><label className="full vault-switch-row"><input className="sr-only" type="checkbox" name="favorite" aria-label="收藏此条目" defaultChecked={value.favorite} /><span className="vault-switch-copy"><Star size={18} /><span><strong>收藏此条目</strong><small>收藏后将在列表中优先展示</small></span></span><span className="vault-switch-track" aria-hidden="true"><span /></span></label>{!authorized && <div className="vault-editor-reauth full"><p className="alert error" role="alert">敏感操作验证已过期，当前输入已保留。请重新验证后再保存。</p><div className="vault-editor-reauth-controls"><input type="password" name="vault_reauth_password" aria-label="重新验证登录密码" placeholder="登录密码（仅用于重新验证）" autoComplete="off" value={reauthPassword} onChange={(event) => setReauthPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); if (!busy && reauthPassword) void renewAuthorization(); } }} /><button type="button" className="button" disabled={busy || !reauthPassword} onClick={() => void renewAuthorization()}>重新验证</button></div></div>}{error && <div className="alert error full">{error}</div>}<div className="modal-actions full"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy || !authorized}><CheckCircle2 size={17} />保存</button></div></form></section></div>;
}

function VaultPage({ children }: { children: React.ReactNode }) { return <div className="page vault-page">{children}</div>; }
function readLegacyLocal(): Array<Record<string, unknown>> { try { const value = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? "[]"); return Array.isArray(value) ? value : []; } catch { return []; } }
function legacySecret(item: Record<string, unknown>): VaultSecret { return { site: String(item.site ?? item.site_name ?? ""), url: String(item.url ?? item.site_url ?? ""), username: String(item.username ?? ""), password: String(item.password ?? ""), category: String(item.category ?? ""), notes: String(item.notes ?? ""), favorite: Boolean(item.favorite ?? item.is_favorite) }; }
function sameSecret(left: VaultSecret, right: VaultSecret): boolean { return left.site === right.site && left.url === right.url && left.username === right.username && left.password === right.password && left.category === right.category && left.notes === right.notes && left.favorite === right.favorite; }
