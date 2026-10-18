import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BookOpenText, Building2, CheckCircle2, Clock3, KeyRound,
  ListTodo, PackageOpen, ScrollText, ShieldCheck, Sparkles, TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

type Stats = Record<"script_count" | "article_count" | "task_total" | "task_pending" | "task_overdue" | "customer_count" | "resource_count" | "password_count", number>;
type Task = { id: number; title: string; priority: string; due_date?: string; is_overdue: number };

const numberFormat = new Intl.NumberFormat("zh-CN");

export function Dashboard() {
  const stats = useQuery({ queryKey: ["dashboard", "stats"], queryFn: () => api<Stats>("/api/dashboard/stats") });
  const tasks = useQuery({ queryKey: ["dashboard", "tasks"], queryFn: () => api<Task[]>("/api/dashboard/recent-tasks") });
  if (stats.isLoading || tasks.isLoading) return <Page><LoadingState label="正在整理工作台" /></Page>;
  if (stats.error || tasks.error) return <Page><ErrorState message="概览加载失败" retry={() => { void stats.refetch(); void tasks.refetch(); }} /></Page>;

  const data = stats.data!;
  const cards = [
    { label: "脚本资产", value: data.script_count, hint: "可复用运维脚本", to: "/scripts", icon: ScrollText, tone: "blue" },
    { label: "知识文章", value: data.article_count, hint: "已沉淀技术文档", to: "/articles", icon: BookOpenText, tone: "violet" },
    { label: "待处理任务", value: data.task_pending, hint: `${data.task_total} 项任务总计`, to: "/tasks", icon: ListTodo, tone: "amber" },
    { label: "客户项目", value: data.customer_count, hint: "客户及项目信息", to: "/customers", icon: Building2, tone: "cyan" },
    { label: "资源索引", value: data.resource_count, hint: "工具、安装包与入口", to: "/resources", icon: PackageOpen, tone: "emerald" },
    { label: "保险箱条目", value: data.password_count, hint: "客户端加密保存", to: "/vault", icon: KeyRound, tone: "rose" },
  ];
  const inventory = [
    { label: "脚本", value: data.script_count, color: "var(--chart-blue)" },
    { label: "知识", value: data.article_count, color: "var(--chart-violet)" },
    { label: "资源", value: data.resource_count, color: "var(--chart-emerald)" },
    { label: "客户", value: data.customer_count, color: "var(--chart-cyan)" },
  ];
  const largest = Math.max(1, ...inventory.map((item) => item.value));
  const date = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(new Date());

  return <Page>
    <section className="dashboard-hero">
      <div>
        <div className="hero-kicker"><Sparkles size={15} /> {date}</div>
        <h1>今天的工作台</h1>
        <p>集中查看 DBA 资产、待办工作和安全状态。</p>
      </div>
      <div className="hero-security"><ShieldCheck size={22} /><span><strong>本机数据受保护</strong><small>仅回环地址 · 已启用身份验证</small></span></div>
    </section>

    <section className="stat-grid" aria-label="数据摘要">
      {cards.map(({ label, value, hint, to, icon: Icon, tone }) => <Link className={`stat-card tone-${tone}`} to={to} key={label}>
        <span className="stat-icon"><Icon size={20} strokeWidth={1.9} /></span>
        <span className="stat-copy"><small>{label}</small><strong>{numberFormat.format(value)}</strong><em>{hint}</em></span>
        <ArrowRight className="stat-arrow" size={17} aria-hidden="true" />
      </Link>)}
    </section>

    <div className="dashboard-grid">
      <section className="panel task-panel">
        <div className="panel-title">
          <div><p className="eyebrow">PRIORITY QUEUE</p><h2>近期未完成任务</h2></div>
          <Link className="text-link" to="/tasks">查看全部 <ArrowRight size={15} /></Link>
        </div>
        {!tasks.data?.length ? <EmptyState title="任务队列已清空" description="暂时没有待处理任务，可以专注处理当前工作。" icon={CheckCircle2} /> : <ul className="task-list">{tasks.data.map((task) => <li key={task.id}>
          <span className={`task-status-icon${task.is_overdue ? " overdue" : ""}`}>{task.is_overdue ? <TriangleAlert size={17} /> : <Clock3 size={17} />}</span>
          <span className="task-copy"><strong>{task.title}</strong><small>{task.priority}优先级{task.due_date ? ` · 截止 ${task.due_date}` : " · 未设置截止日期"}</small></span>
          <span className={`badge${task.is_overdue ? " danger" : ""}`}>{task.is_overdue ? "已逾期" : "待处理"}</span>
        </li>)}</ul>}
      </section>

      <section className="panel inventory-panel">
        <div className="panel-title"><div><p className="eyebrow">ASSET MIX</p><h2>资产构成</h2></div></div>
        <div className="inventory-list">{inventory.map((item) => <div className="inventory-item" key={item.label}>
          <div><span>{item.label}</span><strong>{numberFormat.format(item.value)}</strong></div>
          <div className="progress-track"><span style={{ width: `${Math.max(item.value ? 8 : 0, item.value / largest * 100)}%`, background: item.color }} /></div>
        </div>)}</div>
        <div className="inventory-summary"><span>逾期任务</span><strong className={data.task_overdue ? "text-danger" : ""}>{data.task_overdue}</strong><small>{data.task_overdue ? "建议优先处理" : "当前没有逾期事项"}</small></div>
      </section>
    </div>

    <section className="quick-section">
      <div className="section-heading"><div><p className="eyebrow">QUICK ACCESS</p><h2>常用入口</h2></div><p className="muted">快速进入高频工作模块</p></div>
      <div className="quick-grid">
        <QuickLink to="/scripts" icon={ScrollText} title="管理脚本" detail="检索和维护运维脚本" />
        <QuickLink to="/articles" icon={BookOpenText} title="查阅知识" detail="沉淀排障与实施经验" />
        <QuickLink to="/tasks" icon={ListTodo} title="安排任务" detail="跟踪计划、优先级与截止时间" />
        <QuickLink to="/vault" icon={ShieldCheck} title="打开保险箱" detail="管理客户端加密凭据" />
      </div>
    </section>
  </Page>;
}

function QuickLink({ to, icon: Icon, title, detail }: { to: string; icon: typeof ScrollText; title: string; detail: string }) {
  return <Link className="quick-link" to={to}><span><Icon size={20} /></span><span><strong>{title}</strong><small>{detail}</small></span><ArrowRight size={17} /></Link>;
}

function Page({ children }: { children: React.ReactNode }) { return <div className="page dashboard-page">{children}</div>; }
