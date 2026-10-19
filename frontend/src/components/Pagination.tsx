import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({ page, pages, total, pageSize, onChange, onPageSizeChange }: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const lastPage = Math.max(1, pages);
  const items: Array<number | "previous" | "next"> = [];
  if (lastPage <= 7) {
    for (let number = 1; number <= lastPage; number++) items.push(number);
  } else {
    const start = Math.max(2, Math.min(page - 2, lastPage - 5));
    const end = start + 4;
    items.push(1);
    if (start > 2) items.push(start === 3 ? 2 : "previous");
    for (let number = start; number <= end; number++) items.push(number);
    if (end < lastPage - 1) items.push(end === lastPage - 2 ? lastPage - 1 : "next");
    items.push(lastPage);
  }
  return <nav className="pagination" aria-label="列表分页">
    <span className="sr-only" aria-live="polite">第 {page} / {lastPage} 页</span>
    <select className="page-size-select" aria-label="每页条数" value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
      {[10, 20, 50, 100, 200].map((size) => <option value={size} key={size}>{size}条/页</option>)}
    </select>
    <span className="pagination-total">共 {total} 条</span>
    <div className="pagination-pages">
      <button className="page-step" type="button" aria-label="上一页" title="上一页" disabled={page <= 1} onClick={() => onChange(page - 1)}><ChevronLeft size={14} /></button>
      {items.map((item) => {
        if (typeof item === "number") return <button className="page-number" key={item} type="button" aria-label={`第 ${item} 页`} aria-current={page === item ? "page" : undefined} onClick={() => onChange(item)}>{item}</button>;
        const target = item === "previous" ? Math.max(1, page - 5) : Math.min(lastPage, page + 5);
        return <button className="page-gap" key={item} type="button" aria-label={`${item === "previous" ? "向前" : "向后"}跳转至第 ${target} 页`} title={`${item === "previous" ? "向前" : "向后"}跳转 5 页`} onClick={() => onChange(target)}>···</button>;
      })}
      <button className="page-step" type="button" aria-label="下一页" title="下一页" disabled={page >= lastPage} onClick={() => onChange(page + 1)}><ChevronRight size={14} /></button>
    </div>
  </nav>;
}
