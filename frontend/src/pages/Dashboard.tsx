import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

type Stats = Record<"script_count" | "article_count" | "task_total" | "task_pending" | "task_overdue" | "customer_count" | "resource_count" | "password_count", number>;
type Task = { id: number; title: string; priority: string; due_date?: string; is_overdue: number };

export function Dashboard() {
  const stats = useQuery({ queryKey: ["dashboard", "stats"], queryFn: () => api<Stats>("/api/dashboard/stats") });
  const tasks = useQuery({ queryKey: ["dashboard", "tasks"], queryFn: () => api<Task[]>("/api/dashboard/recent-tasks") });
  if (stats.isLoading || tasks.isLoading) return <Page><LoadingState label="加载概览" /></Page>;
  if (stats.error || tasks.error) return <Page><ErrorState message="概览加载失败" retry={() => { void stats.refetch(); void tasks.refetch(); }} /></Page>;
  const cards = [
    ["脚本", stats.data!.script_count], ["知识文章", stats.data!.article_count],
    ["待处理任务", stats.data!.task_pending], ["逾期任务", stats.data!.task_overdue],
    ["客户", stats.data!.customer_count], ["资源", stats.data!.resource_count],
    ["保险箱条目", stats.data!.password_count],
  ];
  return <Page>
    <header className="page-header"><div><p className="eyebrow">OVERVIEW</p><h1>今天的工作台</h1><p className="muted">真实数据摘要，不显示演示告警或虚构状态。</p></div></header>
    <section className="stat-grid" aria-label="数据摘要">{cards.map(([label, value]) => <article className="stat-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="panel"><div className="panel-title"><div><p className="eyebrow">NEXT</p><h2>近期未完成任务</h2></div></div>
      {!tasks.data?.length ? <EmptyState title="没有待处理任务" description="新建任务后会显示在这里。" /> : <ul className="task-list">{tasks.data.map((task) => <li key={task.id}><span><strong>{task.title}</strong><small>{task.priority}优先级{task.due_date ? ` · ${task.due_date}` : ""}</small></span>{task.is_overdue ? <span className="badge danger">已逾期</span> : <span className="badge">待处理</span>}</li>)}</ul>}
    </section>
  </Page>;
}

function Page({ children }: { children: React.ReactNode }) { return <div className="page">{children}</div>; }
