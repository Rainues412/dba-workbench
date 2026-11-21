import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, BookOpenText, Building2, CalendarDays, CheckCircle2, Clock3, Database, KeyRound,
  ListTodo, PackageOpen, ScrollText, TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { DashboardNumber, useDashboardEntrance } from "../components/DashboardMetrics";
import { api, entityApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useProfile } from "../auth/profile";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { DatabaseLabel, databaseMeta } from "../components/DatabaseLabel";
import { TaskStatusButton, playTaskStatusFeedback, useTaskStatusReducedMotion, type TaskStatusPhase } from "../components/TaskStatusButton";

type Stats = Record<"script_count" | "article_count" | "task_total" | "task_pending" | "task_overdue" | "customer_count" | "resource_count" | "password_count", number>;
type Task = { id: number; revision: number; title: string; priority: string; status: string; due_date?: string; is_overdue: number };
type DatabaseDistribution = { name: DatabaseName; count: number }[];
type TaskCompletion = { task: Task; position: number; phase: TaskStatusPhase };
type DatabaseName = "Oracle" | "MySQL" | "PostgreSQL" | "SQL Server" | "Linux" | "Redis" | "MongoDB" | "其他";

const dateFormat = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" });
const weekdayFormat = new Intl.DateTimeFormat("zh-CN", { weekday: "long" });

const recentTasksKey = ["dashboard", "tasks"] as const;
export function Dashboard() {
  const client = useQueryClient();
  const completions = useRef(new Map<number, TaskCompletion>());
  const [processing, setProcessing] = useState(completions.current);
  const viewAllTasks = useRef<HTMLAnchorElement>(null);
  const reducedMotion = useTaskStatusReducedMotion();
  const [quickError, setQuickError] = useState("");
  const stats = useQuery({ queryKey: ["dashboard", "stats"], queryFn: () => api<Stats>("/api/dashboard/stats") });
  const tasks = useQuery({ queryKey: recentTasksKey, queryFn: ({ signal }) => api<Task[]>("/api/dashboard/recent-tasks", { signal }) });
  const distribution = useQuery({ queryKey: ["dashboard", "database-distribution"], queryFn: () => api<DatabaseDistribution>("/api/dashboard/database-distribution") });
  const entrance = useDashboardEntrance(Boolean(stats.data && tasks.data && distribution.data) && !stats.error && !tasks.error && !distribution.error);
  if (stats.isLoading || tasks.isLoading || distribution.isLoading) return <Page><LoadingState label="正在整理工作台" /></Page>;
  if (stats.error || tasks.error || distribution.error) return <Page><ErrorState message="概览加载失败" retry={() => { void stats.refetch(); void tasks.refetch(); void distribution.refetch(); }} /></Page>;

  const data = stats.data!;
  const cards = [
    { label: "脚本资产", value: data.script_count, to: "/scripts", icon: ScrollText, tone: "blue" },
    { label: "知识文章", value: data.article_count, to: "/articles", icon: BookOpenText, tone: "violet" },
    { label: "待处理任务", value: data.task_pending, hint: data.task_overdue > 0 ? `${data.task_overdue} 项已逾期` : "", to: "/tasks", icon: ListTodo, tone: data.task_overdue ? "rose" : "amber" },
    { label: "客户项目", value: data.customer_count, to: "/customers", icon: Building2, tone: "cyan" },
    { label: "资源索引", value: data.resource_count, to: "/resources", icon: PackageOpen, tone: "emerald" },
    { label: "保险箱条目", value: data.password_count, to: "/vault", icon: KeyRound, tone: "rose" },
  ];
  const largestDatabaseCount = Math.max(1, ...(distribution.data ?? []).map((item) => item.count));

  function setCompletion(id: number, completion?: TaskCompletion) {
    const next = new Map(completions.current);
    if (completion) next.set(id, completion);
    else next.delete(id);
    completions.current = next;
    setProcessing(next);
  }

  async function completeTask(task: Task, position: number, trigger: HTMLButtonElement) {
    if (completions.current.has(task.id)) return;
    setQuickError("");
    setCompletion(task.id, { task, position, phase: "pending" });
    try {
      await playTaskStatusFeedback(entityApi.update("/api/tasks/", task.id, task.revision, { status: "已完成" }), reducedMotion,
        () => setCompletion(task.id, { task, position, phase: "success" }));
      await client.cancelQueries({ queryKey: recentTasksKey });
      if (document.activeElement === trigger) viewAllTasks.current?.focus({ preventScroll: true });
      client.setQueryData<Task[]>(recentTasksKey, (current) => current?.filter((item) => item.id !== task.id));
    } catch {
      setQuickError("任务处理失败，请刷新后重试。");
      return;
    } finally {
      setCompletion(task.id);
    }
    await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["tasks"] })]);
  }

  const recentTasks = [...(tasks.data ?? [])];
  // A concurrent refresh may already omit a task whose success animation is still playing.
  for (const { task, position } of [...processing.values()].sort((first, second) => first.position - second.position)) {
    if (!recentTasks.some((item) => item.id === task.id)) recentTasks.splice(position, 0, task);
  }

  return <Page>
    <DashboardHero />

    <section className="stat-grid" aria-label="数据摘要">
      {cards.map(({ label, value, hint, to, icon: Icon, tone }) => <Link className={`stat-card tone-${tone}`} to={to} key={label}>
        <span className="stat-icon"><Icon size={20} strokeWidth={1.9} /></span>
        <span className="stat-copy"><small>{label}</small><DashboardNumber value={value} progress={entrance} />{hint && <em>{hint}</em>}</span>
      </Link>)}
    </section>

    <div className="dashboard-grid">
      <section className="panel task-panel">
        <div className="panel-title">
          <div><p className="eyebrow">PRIORITY QUEUE</p><h2>近期未完成任务</h2></div>
          <div className="task-panel-heading-actions">{data.task_overdue > 0 && <Link className="dashboard-overdue-summary" to="/tasks"><TriangleAlert size={14} />{data.task_overdue} 项逾期</Link>}<Link ref={viewAllTasks} className="text-link" to="/tasks">查看全部 <ArrowRight size={15} /></Link></div>
        </div>
        {quickError && <div className="alert error" role="alert">{quickError}</div>}
        {!recentTasks.length ? <EmptyState title="任务队列已清空" description="暂时没有待处理任务，可以专注处理当前工作。" icon={CheckCircle2} /> : <ul className="task-list dashboard-task-list" aria-label="未完成任务列表" tabIndex={recentTasks.length > 6 ? 0 : undefined}>{recentTasks.map((task, position) => {
          const priority = getPriorityMeta(task.priority);
          return <li className={`task-priority-${priority.tone}`} key={task.id}>
            <span className={`task-status-icon${task.is_overdue ? " overdue" : ""}`}>{task.is_overdue ? <TriangleAlert size={17} /> : <Clock3 size={17} />}</span>
            <span className="task-copy"><strong title={task.title}>{task.title}</strong><small>{task.due_date ? `截止 ${task.due_date}` : "未设置截止日期"}</small></span>
            <span className="task-badges">
              <span className={`priority-badge ${priority.tone}`}>{priority.label}</span>
              <span className={`badge${task.status === "进行中" ? " status-info" : ""}`}>{task.status}</span>
              {Boolean(task.is_overdue) && <span className="badge danger">已逾期</span>}
            </span>
            <TaskStatusButton phase={processing.get(task.id)?.phase} title="标记为已完成" accessibleLabel={`完成任务：${task.title}`} onClick={(trigger) => void completeTask(task, position, trigger)} />
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
              <div className="progress-track" aria-hidden="true"><motion.span style={{ width: `${width}%`, background: meta.color, scaleX: entrance, originX: 0 }} /></div>
              <DashboardNumber value={item.count} progress={entrance} />
            </div>
          </article>;
        })}</div>
      </section>
    </div>

  </Page>;
}

function DashboardHero() {
  const { session } = useAuth();
  const { data: profile } = useProfile(session?.user?.id);
  const displayName = profile?.display_name || session?.user?.username;
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const greeting = greetingForHour(now.getHours());
  return <section className="dashboard-hero">
    <div className="hero-copy">
      <h1>{displayName ? `${greeting}，${displayName}` : greeting}</h1>
      <div className="hero-kicker"><CalendarDays size={15} aria-hidden="true" /> {dateFormat.format(now)} · {weekdayFormat.format(now)}</div>
    </div>
    <svg className="hero-data-art" viewBox="0 0 570 175" fill="none" aria-hidden="true" focusable="false">
      <g stroke="currentColor" strokeWidth="1.2" opacity=".28">
        <path d="M10 113H141Q151 113 151 103V66Q151 56 161 56H271M24 145H213Q223 145 223 135V113Q223 103 233 103H326M121 23H189Q199 23 199 33V56M336 56H393Q403 56 403 46V24Q403 14 413 14H570M365 103H443Q453 103 453 113V143Q453 153 463 153H570M403 56V95Q403 105 413 105H506" />
        <g fill="currentColor" fillOpacity=".12">
          <rect x="271" y="35" width="65" height="43" rx="9" />
          <rect x="326" y="82" width="39" height="43" rx="8" />
          <rect x="506" y="85" width="43" height="40" rx="8" />
        </g>
      </g>
      <g stroke="currentColor" strokeWidth="1.2" opacity=".4">
        <ellipse cx="303.5" cy="47" rx="13" ry="4" />
        <path d="M290.5 47V64C290.5 69.3 316.5 69.3 316.5 64V47M290.5 55.5C290.5 60.8 316.5 60.8 316.5 55.5" />
        <path d="M339 94H352M339 101H352M339 108H347M518 98H537M518 105H531" strokeLinecap="round" />
      </g>
      <g fill="currentColor" opacity=".4">
        <circle cx="151" cy="113" r="3" />
        <circle cx="199" cy="56" r="3" />
        <circle cx="223" cy="145" r="3" />
        <circle cx="403" cy="56" r="3.5" />
        <circle cx="453" cy="103" r="3" />
        <circle cx="480" cy="14" r="2.5" />
        <circle cx="496" cy="153" r="2.5" />
      </g>
    </svg>
  </section>;
}

function greetingForHour(hour: number) {
  if (hour < 5 || hour >= 18) return "晚上好";
  if (hour < 11) return "早上好";
  if (hour < 13) return "中午好";
  return "下午好";
}

function getPriorityMeta(priority: string) {
  if (["P0", "高", "紧急"].includes(priority)) return { tone: "high", label: priority === "P0" ? "P0 紧急" : "高优先级" };
  if (["P1", "中", "重要"].includes(priority)) return { tone: "medium", label: priority === "P1" ? "P1 重要" : "中优先级" };
  if (["P2", "低", "一般"].includes(priority)) return { tone: "low", label: priority === "P2" ? "P2 一般" : "低优先级" };
  return { tone: "neutral", label: priority || "未设置优先级" };
}

function Page({ children }: { children: React.ReactNode }) { return <div className="page dashboard-page">{children}</div>; }
