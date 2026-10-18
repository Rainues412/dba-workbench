import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const navigation = [
  ["/", "概览", "⌂"],
  ["/scripts", "脚本", "⌘"],
  ["/articles", "知识库", "▤"],
  ["/resources", "资源与快捷入口", "◇"],
  ["/tasks", "任务", "✓"],
  ["/customers", "客户", "◎"],
  ["/vault", "密码保险箱", "▣"],
];

export function Shell() {
  const { session, logout } = useAuth();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark small">DB</span><span><strong>DBA 工作台</strong><small>安全本地版</small></span></div>
        <nav aria-label="主导航">
          {navigation.map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <span aria-hidden="true">{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="muted">{session?.user?.username}</span>
          <button className="button ghost" onClick={() => void logout()}>退出登录</button>
        </div>
      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
  );
}
