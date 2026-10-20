import { useEffect, useState } from "react";
import {
  BookOpenText, Building2, ChevronRight, HardDrive, LayoutDashboard,
  ListTodo, LogOut, Moon, PackageOpen, PanelLeftClose, PanelLeftOpen,
  ScrollText, ShieldCheck, Sun,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { GlobalSearch } from "./GlobalSearch";
import { DataBackup } from "./DataBackup";

const navigation = [
  { to: "/", label: "工作台", description: "数据概览", icon: LayoutDashboard },
  { to: "/articles", label: "知识库", description: "文档沉淀", icon: BookOpenText },
  { to: "/scripts", label: "脚本库", description: "运维脚本", icon: ScrollText },
  { to: "/resources", label: "资源中心", description: "工具与入口", icon: PackageOpen },
  { to: "/tasks", label: "任务管理", description: "计划与进度", icon: ListTodo },
  { to: "/customers", label: "客户项目", description: "客户与联系人", icon: Building2 },
  { to: "/vault", label: "密码保险箱", description: "客户端加密", icon: ShieldCheck },
];

export function Shell() {
  const { session, logout } = useAuth();
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
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand-row">
          <NavLink to="/" className="brand" aria-label="返回工作台" title={collapsed ? "返回工作台" : undefined}>
            <span className="brand-mark small"><HardDrive size={20} strokeWidth={2.2} /></span>
            <span className="brand-copy"><strong>DBA 工作台</strong><small>LOCAL OPERATIONS</small></span>
          </NavLink>
          <button className="sidebar-toggle" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "展开侧栏" : "收起侧栏"} title={collapsed ? "展开侧栏" : "收起侧栏"}>
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        <div className="nav-section-label">工作区</div>
        <nav aria-label="主导航">
          {navigation.map(({ to, label, description, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} aria-label={label} title={collapsed ? `${label}：${description}` : undefined} className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <span className="nav-icon" aria-hidden="true"><Icon size={19} strokeWidth={1.9} /></span>
              <span className="nav-copy"><strong>{label}</strong><small>{description}</small></span>
              <ChevronRight className="nav-chevron" size={15} aria-hidden="true" />
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-card">
            <span className="avatar" aria-hidden="true">{session?.user?.username?.slice(0, 1).toUpperCase()}</span>
            <span className="user-copy"><strong>{session?.user?.username}</strong><small>本机 Owner</small></span>
            <button className="icon-button sidebar-action" onClick={() => void logout()} aria-label="退出登录" title="退出登录"><LogOut size={18} /></button>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-title"><span>{current.label}</span><small>{current.description}</small></div>
          <div className="topbar-actions">
            <GlobalSearch />
            <DataBackup />
            <span className="local-status"><span className="status-dot" />本机安全模式</span>
            <button className="icon-button topbar-button" onClick={() => setTheme((value) => value === "light" ? "dark" : "light")} aria-label={theme === "light" ? "切换到深色模式" : "切换到浅色模式"} title={theme === "light" ? "深色模式" : "浅色模式"}>
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
      </div>
    </div>
  );
}
