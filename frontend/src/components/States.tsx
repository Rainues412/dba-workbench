import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export function LoadingState({ label = "加载中" }: { label?: string }) {
  return <div className="state-card" role="status"><span className="spinner" /><div><strong>{label}</strong><p>请稍候，正在读取本机数据…</p></div></div>;
}

export function TableSkeleton() {
  return <div className="skeleton-table" role="status" aria-label="正在加载列表" aria-busy="true">
    {Array.from({ length: 5 }, (_, index) => <span key={index} className="skeleton-line" />)}
  </div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-card error" role="alert"><span className="state-icon"><AlertTriangle size={25} /></span><div><h3>{message}</h3><p>请求没有成功，请检查服务状态后重试。</p></div>{retry && <button className="button" onClick={retry}><RefreshCw size={16} />重试</button>}</div>;
}

export function EmptyState({ title, description, icon: Icon = Inbox }: { title: string; description: string; icon?: LucideIcon }) {
  return <div className="state-card"><span className="state-icon"><Icon size={26} /></span><div><h3>{title}</h3><p>{description}</p></div></div>;
}
