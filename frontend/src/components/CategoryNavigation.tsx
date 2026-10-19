import { Database, FolderOpen, Layers3 } from "lucide-react";
import { DatabaseLabel, databaseMeta } from "./DatabaseLabel";
import { ErrorState, LoadingState } from "./States";

export type Classification = {
  databaseField: string;
  categoryField?: string;
  categoryLabel?: string;
};

export type Facets = { total: number; items: Array<Record<string, string | number>> };

export function CategoryNavigation({ classification, data, loading, error, retry, database, category, onChange }: {
  classification: Classification;
  data?: Facets;
  loading: boolean;
  error: boolean;
  retry: () => void;
  database: string;
  category: string;
  onChange: (database: string, category: string) => void;
}) {
  if (loading) return <section className="panel"><LoadingState label="正在读取分类" /></section>;
  if (error) return <section className="panel"><ErrorState message="分类加载失败" retry={retry} /></section>;
  const { databaseField, categoryField, categoryLabel } = classification;
  const databaseCounts = new Map<string, number>();
  const categoryCounts = new Map<string, number>();
  for (const row of data?.items ?? []) {
    const db = String(row[databaseField] ?? "");
    const count = Number(row.count);
    if (db) databaseCounts.set(db, (databaseCounts.get(db) ?? 0) + count);
    if (categoryField && (!database || db === database)) {
      const name = String(row[categoryField] ?? "");
      if (name) categoryCounts.set(name, (categoryCounts.get(name) ?? 0) + count);
    }
  }
  const databaseNames = [...new Set([...Object.keys(databaseMeta), ...databaseCounts.keys()])];
  const categoryTotal = database ? databaseCounts.get(database) ?? 0 : data?.total ?? 0;
  return <section className="panel classification-panel" aria-label="分类浏览">
    <div className="classification-heading"><div><Layers3 size={18} /><h2>分类浏览</h2></div><span className="muted">按原有分类查找记录</span></div>
    <div className="database-filter-grid" role="group" aria-label="数据库分类">
      <button className="database-filter" type="button" aria-pressed={!database} onClick={() => onChange("", "")}>
        <span className="database-label"><Database size={19} /><strong>全部数据库</strong></span><span className="classification-count">{data?.total ?? 0}</span>
      </button>
      {databaseNames.map((name) => <button className="database-filter" type="button" key={name} aria-pressed={database === name} onClick={() => onChange(name, "")}>
        <DatabaseLabel name={name} /><span className="classification-count">{databaseCounts.get(name) ?? 0}</span>
      </button>)}
    </div>
    {categoryField && <div className="category-filter-row" role="group" aria-label={categoryLabel}>
      <span className="category-filter-label"><FolderOpen size={16} />{database ? `${database} · ` : ""}{categoryLabel}</span>
      <div className="category-filter-options">
        <button className="category-filter" type="button" aria-pressed={!category} onClick={() => onChange(database, "")}>全部<span>{categoryTotal}</span></button>
        {[...categoryCounts].sort(([a], [b]) => a.localeCompare(b, "zh-CN")).map(([name, count]) => <button className="category-filter" key={name} type="button" aria-pressed={category === name} onClick={() => onChange(database, name)}>{name}<span>{count}</span></button>)}
      </div>
    </div>}
  </section>;
}
