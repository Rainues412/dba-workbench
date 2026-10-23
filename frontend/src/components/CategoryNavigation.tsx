import { FolderOpen, Layers3 } from "lucide-react";
import { databaseMeta } from "./DatabaseLabel";
import { DatabaseFilter } from "./DatabaseFilter";
import { ErrorState, LoadingState } from "./States";

export type Classification = {
  databaseField: string;
  categoryField?: string;
  categoryLabel?: string;
};

export type Facets = { total: number; items: Array<Record<string, string | number>> };

export function CategoryNavigation({ classification, data, loading, error, retry, database, category, categoryOptions = [], onChange }: {
  classification: Classification;
  data?: Facets;
  loading: boolean;
  error: boolean;
  retry: () => void;
  database: string;
  category: string;
  categoryOptions?: string[];
  onChange: (database: string, category: string) => void;
}) {
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
  const databaseNames = [...new Set([...Object.keys(databaseMeta), ...databaseCounts.keys(), database].filter(Boolean))];
  const categoryTotal = database ? databaseCounts.get(database) ?? 0 : data?.total ?? 0;
  const categories = [...new Set([...categoryOptions, ...(categoryField ? (data?.items ?? []).map((row) => String(row[categoryField] ?? "")) : []), category].filter(Boolean))];
  return <section className="panel library-categories" aria-label="分类浏览">
    <h2><Layers3 size={16} />分类浏览</h2>
    <div role="group" aria-label="数据库分类">
      <DatabaseFilter value={database} names={databaseNames} counts={databaseCounts} total={data?.total ?? 0} onChange={(value) => onChange(value, "")} />
    </div>
    {loading && <LoadingState label="正在读取分类" />}
    {error && <ErrorState message="分类加载失败" retry={retry} />}
    {categoryField && <div className="category-filter-row" role="group" aria-label={categoryLabel}>
      <span className="category-filter-label"><FolderOpen size={15} />{categoryLabel}</span>
      <div className="category-filter-options">
        <button className="category-filter" type="button" aria-pressed={!category} onClick={() => onChange(database, "")}>全部<span>{categoryTotal}</span></button>
        {categories.map((name) => <button className="category-filter" key={name} type="button" title={name} aria-pressed={category === name} onClick={() => onChange(database, name)}><strong>{name}</strong><span>{categoryCounts.get(name) ?? 0}</span></button>)}
      </div>
    </div>}
  </section>;
}
