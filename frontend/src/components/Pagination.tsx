import { FormEvent, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({ page, pages, onChange }: { page: number; pages: number; onChange: (page: number) => void }) {
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const lastPage = Math.max(1, pages);
  function jump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requested = Number(target);
    if (!target.trim() || !Number.isInteger(requested) || requested < 1 || requested > lastPage) {
      setError(`请输入 1 至 ${lastPage} 的整数页码`);
      return;
    }
    setError("");
    setTarget("");
    onChange(requested);
  }
  return <nav className="pagination" aria-label="列表分页">
    <span className="page-indicator" aria-live="polite">第 <strong>{page}</strong> / {lastPage} 页</span>
    <div className="pagination-controls">
      <div className="pagination-buttons">
        <button className="button pagination-button" aria-label="上一页" disabled={page <= 1} onClick={() => onChange(page - 1)}><ChevronLeft size={17} />上一页</button>
        <button className="button pagination-button" aria-label="下一页" disabled={page >= lastPage} onClick={() => onChange(page + 1)}>下一页<ChevronRight size={17} /></button>
      </div>
      <form className="page-jump" onSubmit={jump} noValidate>
        <label htmlFor="page-jump-input">跳至</label>
        <input id="page-jump-input" aria-label="跳转页码" type="number" min="1" max={lastPage} step="1" inputMode="numeric" placeholder={String(page)} value={target} onChange={(event) => { setTarget(event.target.value); setError(""); }} aria-invalid={!!error} aria-describedby={error ? "page-jump-error" : undefined} />
        <span>页</span><button className="button pagination-button" type="submit">跳转</button>
      </form>
    </div>
    {error && <p className="page-jump-error" role="alert" id="page-jump-error">{error}</p>}
  </nav>;
}
