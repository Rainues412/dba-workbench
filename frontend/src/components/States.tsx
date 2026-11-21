import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

export function LoadingState({ label = "加载中" }: { label?: string }) {
  return <div className="state-card" role="status"><span className="spinner" /><div><strong>{label}</strong><p>请稍候，正在读取本机数据…</p></div></div>;
}

export function SkeletonBlock({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <span className={`skeleton-block ${className}`} style={style} aria-hidden="true" />;
}

export function SkeletonState({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  return <div className={`skeleton-state ${className}`} role="status" aria-label={label} aria-busy="true">{children}</div>;
}

export function TableSkeleton({ variant = "library" }: { variant?: "library" | "tasks" | "customers" }) {
  return <SkeletonState label="正在加载列表" className={`skeleton-table skeleton-table-${variant}`}>
    {Array.from({ length: 5 }, (_, index) => <div className="skeleton-record" key={index} aria-hidden="true">
      <SkeletonBlock className="skeleton-record-icon" />
      <div className="skeleton-record-copy"><SkeletonBlock className="skeleton-title" style={{ width: `${[72, 86, 65, 78, 69][index]}%` }} /><SkeletonBlock className="skeleton-description" /><div className="skeleton-tags"><SkeletonBlock /><SkeletonBlock /></div></div>
      <div className="skeleton-record-end"><SkeletonBlock className="skeleton-tag" /><SkeletonBlock className="skeleton-caption" /></div>
    </div>)}
  </SkeletonState>;
}

export function ContentSkeleton({ label = "正在加载内容", className = "" }: { label?: string; className?: string }) {
  return <SkeletonState label={label} className={`skeleton-content ${className}`}>
    <SkeletonBlock className="skeleton-content-heading" />
    {Array.from({ length: 7 }, (_, index) => <SkeletonBlock key={index} style={{ width: `${[94, 86, 72, 92, 80, 89, 57][index]}%` }} />)}
  </SkeletonState>;
}

export function CardsSkeleton() {
  return <SkeletonState label="正在加载条目" className="vault-grid skeleton-cards">
    {Array.from({ length: 6 }, (_, index) => <div className="vault-card" key={index} aria-hidden="true"><SkeletonBlock className="skeleton-title" /><SkeletonBlock className="skeleton-description" /><SkeletonBlock /><SkeletonBlock className="skeleton-caption" /></div>)}
  </SkeletonState>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-card error" role="alert"><span className="state-icon"><AlertTriangle size={25} /></span><div><h3>{message}</h3><p>请求没有成功，请检查服务状态后重试。</p></div>{retry && <button className="button" onClick={retry}><RefreshCw size={16} />重试</button>}</div>;
}

export function EmptyState({ title, description, icon: Icon = Inbox }: { title: string; description: string; icon?: LucideIcon }) {
  return <div className="state-card"><span className="state-icon"><Icon size={26} /></span><div><h3>{title}</h3><p>{description}</p></div></div>;
}
