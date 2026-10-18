export function LoadingState({ label = "加载中" }: { label?: string }) {
  return <div className="state-card" role="status"><span className="spinner" />{label}…</div>;
}

export function TableSkeleton() {
  return <div className="skeleton-table" role="status" aria-label="正在加载列表" aria-busy="true">
    {Array.from({ length: 5 }, (_, index) => <span key={index} className="skeleton-line" />)}
  </div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-card error" role="alert"><p>{message}</p>{retry && <button className="button" onClick={retry}>重试</button>}</div>;
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="state-card"><h3>{title}</h3><p className="muted">{description}</p></div>;
}
