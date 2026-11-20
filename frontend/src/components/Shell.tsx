import { type CSSProperties, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  BookOpenText, Building2, LayoutDashboard,
  Command, ListTodo, Moon, PackageOpen, PanelLeftClose, PanelLeftOpen, Plus,
  ScrollText, Settings, ShieldCheck, Sun,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import brandIcon from "../../../assets/dba-workbench-icon.svg";
import { AccountProfile } from "./AccountProfile";
import { DesktopDragRegion, DesktopWindowControls, useDesktopWindow } from "./DesktopWindowControls";
import { GlobalSearch } from "./GlobalSearch";
import { SelectionIndicator, SelectionMotion } from "./SelectionMotion";
import { savePreference, usePreference } from "../preferences";
import { WorkbenchCommands, type WorkbenchCommand } from "./WorkbenchCommands";
import { WorkbenchSettings } from "./WorkbenchSettings";
import "../workbench-settings.css";

const navigationGroups = [
  { label: "工作区", items: [
    { to: "/", label: "工作台", description: "数据概览", icon: LayoutDashboard },
    { to: "/tasks", label: "任务管理", description: "计划与进度", icon: ListTodo },
    { to: "/customers", label: "客户项目", description: "客户与联系人", icon: Building2 },
  ] },
  { label: "资料", items: [
    { to: "/articles", label: "知识库", description: "文档沉淀", icon: BookOpenText },
    { to: "/scripts", label: "脚本库", description: "运维脚本", icon: ScrollText },
    { to: "/resources", label: "资源中心", description: "工具与入口", icon: PackageOpen },
  ] },
  { label: "安全", items: [
    { to: "/vault", label: "密码保险箱", description: "客户端加密", icon: ShieldCheck },
  ] },
];
const navigation = navigationGroups.flatMap(({ items }) => items);

export function Shell() {
  const { session, logout } = useAuth();
  const desktopWindow = useDesktopWindow();
  const location = useLocation();
  const navigate = useNavigate();
  const position = usePreference("navigation");
  const horizontal = position === "top" || position === "bottom";
  const collapsed = usePreference("sidebarCollapsed") === "true" && !horizontal;
  const width = Math.min(360, Math.max(180, Number(usePreference("sidebarWidth")) || 220));
  const density = usePreference("density");
  const reduceMotion = usePreference("reduceMotion");
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const [dialog, setDialog] = useState<"settings" | "commands" | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    localStorage.getItem("dba-ui-theme") === "dark" ? "dark" : "light"
  );
  const current = navigation.find((item) => item.to === location.pathname) ?? navigation[0];
  const commands: WorkbenchCommand[] = [
    ...navigation.map(({ to, label, icon }) => ({ title: `打开${label}`, section: "导航", icon, run: () => navigate(to) })),
    { title: "新建脚本", section: "创建", icon: Plus, run: () => navigate("/scripts?create=1") },
    { title: "新建文章", section: "创建", icon: Plus, run: () => navigate("/articles?create=1") },
    { title: "打开设置", section: "偏好", icon: Settings, run: () => setDialog("settings") },
  ];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("dba-ui-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.reduceMotion = reduceMotion;
    return () => {
      delete document.documentElement.dataset.density;
      delete document.documentElement.dataset.reduceMotion;
    };
  }, [density, reduceMotion]);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.repeat || document.querySelector("dialog[open]:not(.workbench-settings, .command-palette)")) return;
      const target = event.key === "," ? "settings" : event.shiftKey && event.key.toLowerCase() === "p" ? "commands" : null;
      if (!target) return;
      event.preventDefault();
      setDialog((open) => open === target ? null : target);
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const topbarActions = <>
    <GlobalSearch />
    <span className="local-status"><span className="status-dot" />本机安全模式</span>
    <button className="icon-button topbar-button" onClick={() => setTheme((value) => value === "light" ? "dark" : "light")} aria-label={theme === "light" ? "切换到深色模式" : "切换到浅色模式"} title={theme === "light" ? "深色模式" : "浅色模式"}>
      {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
    </button>
    {desktopWindow && <DesktopWindowControls actions={desktopWindow} settingsAvailable={Boolean(session?.vault_password_only)} />}
  </>;

  return (
    <div className={`app-shell navigation-${position}${desktopWindow ? " desktop-shell" : ""}${collapsed ? " sidebar-collapsed" : ""}${dragWidth !== null ? " sidebar-resizing" : ""}`}
      style={{ "--sidebar-width": `${dragWidth ?? width}px` } as CSSProperties}>
      <aside className="sidebar">
        <div className="brand-row">
          <NavLink to="/" className="brand" aria-label="返回工作台" title="返回工作台">
            <img className="brand-mark small" src={brandIcon} alt="" />
            <span className="brand-copy">DBA 工作台</span>
          </NavLink>
          {!horizontal && <button type="button" className="sidebar-toggle" onClick={() => savePreference("sidebarCollapsed", String(!collapsed))} aria-label={collapsed ? "展开侧栏" : "收起侧栏"} title={collapsed ? "展开侧栏" : "收起侧栏"}>
            {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
          </button>}
        </div>

        <SelectionMotion>
          <motion.nav layoutScroll aria-label="主导航">
            {navigationGroups.map(({ label: groupLabel, items }) => (
              <div className="nav-group" role="group" aria-label={groupLabel} key={groupLabel}>
                <div className="nav-section-label" aria-hidden="true">{groupLabel}</div>
                {items.map(({ to, label, icon: Icon }) => (
                  <NavLink key={to} to={to} end={to === "/"} aria-label={label} title={collapsed ? label : undefined} className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    {({ isActive }) => <>
                      {isActive && <SelectionIndicator className="nav-active-indicator" radius="inherit" />}
                      <Icon className="nav-icon" size={14} strokeWidth={1.9} aria-hidden="true" />
                      <span className="nav-copy">{label}</span>
                    </>}
                  </NavLink>
                ))}
              </div>
            ))}
          </motion.nav>
        </SelectionMotion>

        <div className="sidebar-foot">
          <button type="button" className="workbench-settings-entry" aria-haspopup="dialog" aria-label="快捷操作" title="快捷操作（Ctrl+Shift+P）" onClick={() => setDialog("commands")}><Command /><span>快捷操作</span></button>
          <button type="button" className="workbench-settings-entry navigation-settings" aria-haspopup="dialog" aria-label="设置" title="设置（Ctrl+,）" onClick={() => setDialog("settings")}><Settings /><span>设置</span></button>
          {session?.user?.id !== undefined && <AccountProfile key={session.user.id} userId={session.user.id}
            username={session.user.username} logout={session.desktop ? undefined : logout} />}
        </div>
        {position === "top" && <div className="top-navigation-actions"><DesktopDragRegion actions={desktopWindow}>{null}</DesktopDragRegion><div className="topbar-actions">{topbarActions}</div></div>}
        {!horizontal && !collapsed && <div className="sidebar-resize" role="separator" tabIndex={0} aria-label="调整主侧边栏宽度" aria-orientation="vertical"
          aria-valuemin={180} aria-valuemax={360} aria-valuenow={dragWidth ?? width}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            drag.current = { x: event.clientX, width };
            setDragWidth(width);
          }}
          onPointerMove={(event) => {
            if (drag.current) setDragWidth(Math.max(180, Math.min(360, drag.current.width + (event.clientX - drag.current.x) * (position === "right" ? -1 : 1))));
          }}
          onPointerUp={() => { if (drag.current && dragWidth !== null) savePreference("sidebarWidth", String(dragWidth)); }}
          onLostPointerCapture={() => { drag.current = null; setDragWidth(null); }}
          onKeyDown={(event) => {
            if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
            event.preventDefault();
            const step = (event.key === "ArrowRight" ? 10 : -10) * (position === "right" ? -1 : 1);
            savePreference("sidebarWidth", String(Math.min(360, Math.max(180, width + step))));
          }} />}
      </aside>

      <div className="workspace">
        {position !== "top" && <header className={desktopWindow ? "topbar desktop-topbar" : "topbar"}>
          <DesktopDragRegion actions={desktopWindow}><span title={current.label}>{current.label}</span><small>{current.description}</small></DesktopDragRegion>
          <div className="topbar-actions">{topbarActions}</div>
        </header>}
        <main className="main-content"><Outlet /></main>
      </div>
      {dialog === "commands" && <WorkbenchCommands commands={commands} onClose={() => setDialog(null)} />}
      {dialog === "settings" && <WorkbenchSettings desktop={Boolean(session?.vault_password_only)} onClose={() => setDialog(null)} />}
    </div>
  );
}
