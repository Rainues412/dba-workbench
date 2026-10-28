import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, BookOpenText, Building2, CheckCircle2, Clock3, Database, KeyRound,
  ListTodo, PackageOpen, ScrollText, ShieldCheck, Sparkles, TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, entityApi } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { DatabaseLabel, databaseMeta } from "../components/DatabaseLabel";

type Stats = Record<"script_count" | "article_count" | "task_total" | "task_pending" | "task_overdue" | "customer_count" | "resource_count" | "password_count", number>;
type Task = { id: number; revision: number; title: string; priority: string; status: string; due_date?: string; is_overdue: number };
type DatabaseDistribution = { name: DatabaseName; count: number }[];
type DatabaseName = "Oracle" | "MySQL" | "PostgreSQL" | "SQL Server" | "Linux" | "Redis" | "MongoDB" | "其他";

const numberFormat = new Intl.NumberFormat("zh-CN");

export function Dashboard() {
  const client = useQueryClient();
  const [processing, setProcessing] = useState<Set<number>>(new Set());
  const [quickError, setQuickError] = useState("");
  const stats = useQuery({ queryKey: ["dashboard", "stats"], queryFn: () => api<Stats>("/api/dashboard/stats") });
  const tasks = useQuery({ queryKey: ["dashboard", "tasks"], queryFn: () => api<Task[]>("/api/dashboard/recent-tasks") });
  const distribution = useQuery({ queryKey: ["dashboard", "database-distribution"], queryFn: () => api<DatabaseDistribution>("/api/dashboard/database-distribution") });
  if (stats.isLoading || tasks.isLoading || distribution.isLoading) return <Page><LoadingState label="正在整理工作台" /></Page>;
  if (stats.error || tasks.error || distribution.error) return <Page><ErrorState message="概览加载失败" retry={() => { void stats.refetch(); void tasks.refetch(); void distribution.refetch(); }} /></Page>;

  const data = stats.data!;
  const cards = [
    { label: "脚本资产", value: data.script_count, hint: "可复用运维脚本", to: "/scripts", icon: ScrollText, tone: "blue" },
    { label: "知识文章", value: data.article_count, hint: "已沉淀技术文档", to: "/articles", icon: BookOpenText, tone: "violet" },
    { label: "待处理任务", value: data.task_pending, hint: data.task_overdue ? `${data.task_overdue} 项已逾期 · ${data.task_total} 项总计` : `${data.task_total} 项任务总计`, to: "/tasks", icon: ListTodo, tone: data.task_overdue ? "rose" : "amber" },
    { label: "客户项目", value: data.customer_count, hint: "客户及项目信息", to: "/customers", icon: Building2, tone: "cyan" },
    { label: "资源索引", value: data.resource_count, hint: "工具、安装包与入口", to: "/resources", icon: PackageOpen, tone: "emerald" },
    { label: "保险箱条目", value: data.password_count, hint: "客户端加密保存", to: "/vault", icon: KeyRound, tone: "rose" },
  ];
  const largestDatabaseCount = Math.max(1, ...(distribution.data ?? []).map((item) => item.count));
  const date = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(new Date());

  async function completeTask(task: Task) {
    setQuickError("");
    setProcessing((current) => new Set(current).add(task.id));
    try {
      await entityApi.update("/api/tasks/", task.id, task.revision, { status: "已完成" });
      await client.invalidateQueries({ queryKey: ["dashboard"] });
    } catch {
      setQuickError("任务处理失败，请刷新后重试。");
    } finally {
      setProcessing((current) => { const next = new Set(current); next.delete(task.id); return next; });
    }
  }

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
          <div className="task-panel-heading-actions">{data.task_overdue > 0 && <Link className="dashboard-overdue-summary" to="/tasks"><TriangleAlert size={14} />{data.task_overdue} 项逾期</Link>}<Link className="text-link" to="/tasks">查看全部 <ArrowRight size={15} /></Link></div>
        </div>
        {quickError && <div className="alert error" role="alert">{quickError}</div>}
        {!tasks.data?.length ? <EmptyState title="任务队列已清空" description="暂时没有待处理任务，可以专注处理当前工作。" icon={CheckCircle2} /> : <ul className="task-list dashboard-task-list" aria-label="未完成任务列表" tabIndex={tasks.data.length > 6 ? 0 : undefined}>{tasks.data.map((task) => {
          const priority = getPriorityMeta(task.priority);
          return <li className={`task-priority-${priority.tone}`} key={task.id}>
            <span className={`task-status-icon${task.is_overdue ? " overdue" : ""}`}>{task.is_overdue ? <TriangleAlert size={17} /> : <Clock3 size={17} />}</span>
            <span className="task-copy"><strong title={task.title}>{task.title}</strong><small>{task.due_date ? `截止 ${task.due_date}` : "未设置截止日期"}</small></span>
            <span className="task-badges">
              <span className={`priority-badge ${priority.tone}`}>{priority.label}</span>
              <span className={`badge${task.status === "进行中" ? " status-info" : ""}`}>{task.status}</span>
              {Boolean(task.is_overdue) && <span className="badge danger">已逾期</span>}
            </span>
            <button className="task-quick-complete" type="button" title="标记为已完成" aria-label={`完成任务：${task.title}`} disabled={processing.has(task.id)} onClick={() => void completeTask(task)}><CheckCircle2 size={16} /><span>{processing.has(task.id) ? "处理中" : "完成"}</span></button>
          </li>;
        })}</ul>}
      </section>

      <section className="panel database-panel">
        <div className="panel-title"><div><p className="eyebrow">DATABASE MIX</p><h2><Database size={18} />数据库类型分布</h2></div><small className="muted">脚本 + 知识</small></div>
        <div className="database-distribution-grid">{distribution.data?.map((item) => {
          const meta = databaseMeta[item.name];
          const width = Math.max(item.count ? 8 : 0, item.count / largestDatabaseCount * 100);
          return <article className="database-distribution-item" key={item.name}>
            <DatabaseLabel name={item.name} />
            <div className="database-bar-row">
              <div className="progress-track"><span style={{ width: `${width}%`, background: meta.color }} /></div>
              <strong>{numberFormat.format(item.count)}</strong>
            </div>
          </article>;
        })}</div>
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

function getPriorityMeta(priority: string) {
  if (["P0", "高", "紧急"].includes(priority)) return { tone: "high", label: priority === "P0" ? "P0 紧急" : "高优先级" };
  if (["P1", "中", "重要"].includes(priority)) return { tone: "medium", label: priority === "P1" ? "P1 重要" : "中优先级" };
  if (["P2", "低", "一般"].includes(priority)) return { tone: "low", label: priority === "P2" ? "P2 一般" : "低优先级" };
  return { tone: "neutral", label: priority || "未设置优先级" };
}

function Page({ children }: { children: React.ReactNode }) { return <div className="page dashboard-page">{children}</div>; }
