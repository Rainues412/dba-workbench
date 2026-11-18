import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  BookOpenText, Building2, LayoutDashboard,
  ListTodo, Moon, PackageOpen, PanelLeftClose, PanelLeftOpen,
  ScrollText, ShieldCheck, Sun,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import brandIcon from "../../../assets/dba-workbench-icon.svg";
import { AccountProfile } from "./AccountProfile";
import { DesktopDragRegion, DesktopWindowControls, useDesktopWindow } from "./DesktopWindowControls";
import { GlobalSearch } from "./GlobalSearch";
import { SelectionIndicator, SelectionMotion } from "./SelectionMotion";

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
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    localStorage.getItem("dba-ui-theme") === "dark" ? "dark" : "light"
  );
  const current = navigation.find((item) => item.to === location.pathname) ?? navigation[0];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("dba-ui-theme", theme);
  }, [theme]);

  return (
    <div className={`app-shell${desktopWindow ? " desktop-shell" : ""}${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand-row">
          <NavLink to="/" className="brand" aria-label="返回工作台" title="返回工作台">
            <img className="brand-mark small" src={brandIcon} alt="" />
            <span className="brand-copy">DBA 工作台</span>
          </NavLink>
          <button type="button" className="sidebar-toggle" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "展开侧栏" : "收起侧栏"} title={collapsed ? "展开侧栏" : "收起侧栏"}>
            {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
          </button>
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

        {session?.user?.id !== undefined && <AccountProfile key={session.user.id} userId={session.user.id}
          username={session.user.username} logout={session.desktop ? undefined : logout} />}
      </aside>

      <div className="workspace">
        <header className={desktopWindow ? "topbar desktop-topbar" : "topbar"}>
          <DesktopDragRegion actions={desktopWindow}><span title={current.label}>{current.label}</span><small>{current.description}</small></DesktopDragRegion>
          <div className="topbar-actions">
            <GlobalSearch />
            <span className="local-status"><span className="status-dot" />本机安全模式</span>
            <button className="icon-button topbar-button" onClick={() => setTheme((value) => value === "light" ? "dark" : "light")} aria-label={theme === "light" ? "切换到深色模式" : "切换到浅色模式"} title={theme === "light" ? "深色模式" : "浅色模式"}>
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            {desktopWindow && <DesktopWindowControls actions={desktopWindow} />}
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
      </div>
    </div>
  );
}
