import { type FormEvent, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenText, Check, Circle, Database, Info, Keyboard, Monitor, PanelLeft, Power, Settings, X } from "lucide-react";
import { api, VAULT_LOCKED_EVENT } from "../api/client";
import { savePreference, usePreference, type Preference } from "../preferences";
import { desktopVaultApi, useDesktopVaultUnlocked } from "../vault/desktopVault";
import { AppDialog } from "./AppDialog";
import { desktopSettingsApi, useDesktopSettings } from "../desktopSettings";
import { VaultBackupRestore } from "./VaultBackupRestore";

const sections = [
  ["appearance", "外观与阅读", Monitor, "字号 字体 动画 行号 换行 密度"],
  ["navigation", "导航栏", PanelLeft, "菜单 位置 侧栏 左 右 顶部 底部"],
  ["workspace", "工作区", BookOpenText, "脚本 置顶 文档 信息"],
  ["window", "窗口与启动", Power, "开机 自启 静默 窗口 关闭 最小化 托盘"],
  ["security", "密码库安全", Database, "密码 保险箱 主密码 解锁 锁定 安全 数据位置 备份 恢复 导入"],
  ["shortcuts", "快捷键", Keyboard, "按键 搜索 保存 打开"],
  ["about", "关于", Info, "版本 内容"],
] as const;
const shortcuts = [
  ["快捷操作", "Ctrl Shift P"], ["打开设置", "Ctrl ,"], ["全局搜索", "Ctrl K"],
  ["保存脚本", "Ctrl S"], ["代码内查找", "Ctrl F"], ["下一个匹配", "Enter"],
  ["上一个匹配", "Shift Enter"], ["脚本列表移动", "↑ / ↓"],
  ["打开脚本详情", "Ctrl Enter"], ["退出专注 / 关闭查找", "Esc"],
];
type Section = typeof sections[number][0];

export function WorkbenchSettings({ desktop, onClose }: { desktop: boolean; onClose: () => void }) {
  const search = useRef<HTMLInputElement>(null);
  const [section, setSection] = useState<Section>("appearance");
  const [query, setQuery] = useState("");
  const [savedAt, setSavedAt] = useState(0);
  const [error, setError] = useState("");
  const [autoBusy, setAutoBusy] = useState(false);
  const [changing, setChanging] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [windowBusy, setWindowBusy] = useState(false);
  const visible = sections.filter(([id, label, , terms]) =>
    (desktop || id !== "window") && (!query.trim() || `${label} ${terms}`.includes(query.trim())));
  const active = query.trim() ? visible[0]?.[0] : section;
  const client = useQueryClient();
  const windowSettings = useDesktopSettings(desktop && active === "window");
  const unlocked = useDesktopVaultUnlocked();
  const auto = useQuery({ queryKey: ["vault", "auto-status"], queryFn: ({ signal }) => desktopVaultApi.autoStatus(signal), enabled: desktop && active === "security" });
  const diagnostics = useQuery({ queryKey: ["vault", "diagnostics"], queryFn: desktopVaultApi.diagnostics, enabled: desktop && active === "security" });
  const stats = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: () => api<{ script_count: number; article_count: number }>("/api/dashboard/stats"),
    enabled: active === "about",
  });

  useEffect(() => {
    if (!savedAt) return;
    const timer = window.setTimeout(() => setSavedAt(0), 1800);
    return () => window.clearTimeout(timer);
  }, [savedAt]);

  function markSaved() { setError(""); setSavedAt(Date.now()); }
  function update(key: Preference, value: string) {
    try { savePreference(key, value); markSaved(); }
    catch { setSavedAt(0); setError("无法保存偏好，请检查本地存储后重试。"); }
  }
  async function updateWindow(name: "auto_start" | "silent_start" | "close_to_tray", enabled: boolean) {
    if (!windowSettings.data || windowBusy) return;
    setWindowBusy(true); setError(""); setSavedAt(0);
    try {
      client.setQueryData(["desktop", "settings"], await desktopSettingsApi.update({ [name]: enabled }, windowSettings.data.revision));
      markSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "窗口与启动设置保存失败。");
      void windowSettings.refetch();
    } finally { setWindowBusy(false); }
  }
  async function setAutoUnlock(enabled: boolean) {
    setAutoBusy(true); setError("");
    try {
      client.setQueryData(["vault", "auto-status"], await desktopVaultApi.setAutoUnlock(enabled));
      markSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "自动解锁设置保存失败。"); }
    finally { setAutoBusy(false); }
  }
  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next = String(data.get("new_password") ?? "");
    if (next !== data.get("confirm_password")) { setError("两次输入的新主密码不一致。"); return; }
    setPasswordBusy(true); setError("");
    try {
      await desktopVaultApi.changePassword(String(data.get("current_password") ?? ""), next);
      window.dispatchEvent(new Event(VAULT_LOCKED_EVENT));
      await Promise.all([
        client.invalidateQueries({ queryKey: ["vault", "profile"] }),
        client.invalidateQueries({ queryKey: ["vault", "auto-status"] }),
      ]);
      setChanging(false);
      markSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "主密码修改失败。"); }
    finally { setPasswordBusy(false); }
  }

  return <AppDialog className="workbench-settings" labelledBy="workbench-settings-title" onClose={onClose} initialFocus={search}>
    <header><h2 id="workbench-settings-title"><Settings />设置</h2><button type="button" aria-label="关闭设置" onClick={onClose}><X /></button></header>
    <div className="preferences-layout">
      <nav aria-label="设置分类">
        <input ref={search} type="search" aria-label="搜索设置" placeholder="搜索设置" value={query} onChange={(event) => setQuery(event.target.value)} />
        {visible.map(([id, label, Icon]) => <button type="button" key={id} aria-current={id === active ? "page" : undefined}
          onClick={() => { setSection(id); setQuery(""); setError(""); }}><Icon />{label}</button>)}
      </nav>
      <section className="preferences-content" key={active}>
        {!active && <p role="status">没有匹配的设置。</p>}
        {active === "appearance" && <><h3>外观与阅读</h3>
          <SelectPreference label="界面密度" name="density" options={[["compact", "紧凑"], ["comfortable", "舒适"]]} onUpdate={update} />
          <SelectPreference label="代码字号" name="codeSize" options={[["0", "默认 14 px"], ...[12, 13, 14, 15, 16, 17, 18].map((size) => [String(size), `${size} px`] as const)]} onUpdate={update} />
          <TogglePreference label="代码自动换行" name="codeWrap" onUpdate={update} />
          <TogglePreference label="显示代码行号" name="lineNumbers" onUpdate={update} />
          <TogglePreference label="减少动态效果" name="reduceMotion" onUpdate={update} />
        </>}
        {active === "navigation" && <><h3>导航栏</h3>
          <SelectPreference label="导航栏位置" name="navigation" options={[["left", "左侧"], ["right", "右侧"], ["top", "顶部"], ["bottom", "底部"]]} onUpdate={update} />
        </>}
        {active === "workspace" && <><h3>工作区</h3>
          <TogglePreference label="常用脚本自动置顶" detail="近 30 天使用至少 3 次，最多 5 个。" name="autoPinScripts" onUpdate={update} />
          <TogglePreference label="显示文档信息" name="showDocumentInfo" onUpdate={update} />
        </>}
        {active === "window" && <><h3>窗口与启动</h3>
          {windowSettings.isPending && <p role="status">正在读取窗口与启动设置…</p>}
          {windowSettings.isError && <p role="alert">无法读取窗口与启动设置。<button type="button" className="button" onClick={() => void windowSettings.refetch()}>重新读取</button></p>}
          {windowSettings.data && <>
            {([
              ["auto_start", "开机启动", windowSettings.data.startup_conflict ? "启动项指向其他位置，请先在 Windows 中核对。" : "登录当前 Windows 账户后自动运行。"],
              ["silent_start", "静默启动", "启动时仅显示托盘图标，可从托盘或再次打开软件显示窗口。"],
              ["close_to_tray", "关闭时最小化到托盘", windowSettings.data.native_window ? "开启后，关闭窗口仍在后台运行；关闭此选项后将退出软件。" : "此选项需要使用桌面窗口；浏览器模式请从托盘退出软件。"],
            ] as const).map(([name, label, detail]) => <label className="preference-row" key={name}>
              <span><strong>{label}</strong><small>{detail}</small></span>
              <Toggle label={label} checked={windowSettings.data[name]}
                disabled={windowBusy || windowSettings.isFetching || (name === "auto_start" && windowSettings.data.startup_conflict) || (name === "close_to_tray" && !windowSettings.data.native_window)}
                onChange={(enabled) => void updateWindow(name, enabled)} />
            </label>)}
          </>}
        </>}
        {active === "security" && <><h3>密码库安全</h3>{desktop && <>
          <label className="preference-row"><span><strong>在这台电脑上自动解锁</strong><small>使用此 Windows 账户的人可自动访问保险箱。</small>
            {!unlocked && !auto.data?.enabled && <small>请先使用主密码解锁，再开启此选项。</small>}
            {auto.isError && <small role="alert">无法读取本机自动解锁设置。</small>}
          </span><Toggle label="在这台电脑上自动解锁" checked={Boolean(auto.data?.enabled)}
            disabled={autoBusy || !auto.data?.available || (!unlocked && !auto.data?.enabled)} onChange={(enabled) => void setAutoUnlock(enabled)} /></label>
          <SelectPreference label="闲置时自动锁定" detail="锁定后需输入主密码。" name="idleMinutes"
            options={[["0", "不自动锁定"], ["15", "15 分钟"], ["30", "30 分钟"], ["120", "2 小时"]]} onUpdate={update} />
          <div className="preference-row"><strong>修改主密码</strong><button type="button" className="button" onClick={() => { setChanging((value) => !value); setError(""); }}>{changing ? "取消修改" : "修改"}</button></div>
          {changing && <form className="stack settings-password-form" onSubmit={changePassword}>
            <label>当前主密码<input autoFocus name="current_password" type="password" autoComplete="current-password" minLength={9} maxLength={256} required /></label>
            <label>新主密码<input name="new_password" type="password" autoComplete="new-password" minLength={9} maxLength={256} placeholder="至少 9 位" required /></label>
            <label>确认新主密码<input name="confirm_password" type="password" autoComplete="new-password" minLength={9} maxLength={256} required /></label>
            <button type="submit" className="button" disabled={passwordBusy}>{passwordBusy ? "正在保存…" : "保存新主密码"}</button>
          </form>}
          </>}
          <VaultBackupRestore desktop={desktop} />
          {desktop && <section className="vault-data-directory context-details">
            <h4>数据目录</h4>
            {diagnostics.isLoading && <p>正在读取数据目录…</p>}
            {diagnostics.data && <p>{diagnostics.data.database_path.replace(/[^\\/]+$/, "")}</p>}
            {diagnostics.error && <p role="alert">无法读取数据目录。</p>}
          </section>}
        </>}
        {active === "shortcuts" && <><h3>快捷键</h3>{shortcuts.map(([label, key]) =>
          <div className="preference-row" key={label}><strong>{label}</strong><kbd>{key}</kbd></div>)}</>}
        {active === "about" && <><div className="product-identity"><Database /><div><h3>DBA 工作台</h3><span>本地数据库工作空间</span></div></div>
          <dl className="product-facts"><dt>版本</dt><dd>{import.meta.env.VITE_APP_VERSION || "开发版"}</dd><dt>内容</dt>
            <dd>{stats.data ? `${stats.data.script_count} 个脚本 · ${stats.data.article_count} 篇文章` : stats.isError ? "暂时无法读取" : "正在读取…"}</dd>
            <dt>数据保护</dt><dd>服务仅供本机访问；保险箱凭据加密保存，解锁后查看。</dd></dl>
        </>}
      </section>
    </div>
    <footer><span role="status">{savedAt ? <><Check />已保存</> : null}</span>{error && <span role="alert">{error}</span>}<button type="button" className="button" onClick={onClose}>完成</button></footer>
  </AppDialog>;
}

type PreferenceProps = { label: string; detail?: string; name: Preference; onUpdate: (name: Preference, value: string) => void };

function SelectPreference({ label, detail, name, onUpdate, options }: PreferenceProps & { options: readonly (readonly [string, string])[] }) {
  const value = usePreference(name);
  return <label className="preference-row"><span><strong>{label}</strong>{detail && <small>{detail}</small>}</span>
    <select aria-label={label} value={value} onChange={(event) => onUpdate(name, event.target.value)}>
      {options.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
    </select>
  </label>;
}

function TogglePreference({ label, detail, name, onUpdate }: PreferenceProps) {
  const value = usePreference(name);
  return <label className="preference-row"><span><strong>{label}</strong>{detail && <small>{detail}</small>}</span>
    <Toggle label={label} checked={value === "true"} onChange={(checked) => onUpdate(name, String(checked))} />
  </label>;
}

function Toggle({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (enabled: boolean) => void }) {
  return <span className="preference-switch"><input type="checkbox" role="switch" aria-label={label} checked={checked}
    disabled={disabled} onChange={(event) => onChange(event.target.checked)} /><Circle fill="currentColor" aria-hidden="true" /></span>;
}
