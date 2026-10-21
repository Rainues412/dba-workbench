import linuxIcon from "../assets/database/linux.svg";
import mysqlIcon from "../assets/database/mysql.svg";
import mongodbIcon from "../assets/database/mongodb.svg";
import oracleIcon from "../assets/database/oracle.svg";
import otherIcon from "../assets/database/other.svg";
import postgresqlIcon from "../assets/database/postgresql.svg";
import sqlServerIcon from "../assets/database/sqlserver.svg";

export const databaseMeta: Record<string, { color: string; tint: string; icon?: string }> = {
  Oracle: { color: "#dc2626", tint: "#fef2f2", icon: oracleIcon },
  MySQL: { color: "#00618a", tint: "#eaf6fb", icon: mysqlIcon },
  PostgreSQL: { color: "#2563eb", tint: "#eff6ff", icon: postgresqlIcon },
  "SQL Server": { color: "#404040", tint: "#f5f5f5", icon: sqlServerIcon },
  Linux: { color: "#f59e0b", tint: "#fffbeb", icon: linuxIcon },
  Redis: { color: "#dc2626", tint: "#fef2f2" },
  MongoDB: { color: "#00684a", tint: "#e8f7f0", icon: mongodbIcon },
  其他: { color: "#64748b", tint: "#f1f5f9", icon: otherIcon },
};

export function DatabaseLabel({ name }: { name: string }) {
  const meta = databaseMeta[name] ?? databaseMeta["其他"];
  return <span className="database-label" style={{ color: meta.color, background: meta.tint }}>
    <span className="database-logo" aria-hidden="true">
      {meta.icon ? <img src={meta.icon} alt="" /> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="m12 4 8 4-8 4-8-4 8-4Z" />
        <path d="m4 12 8 4 8-4" />
        <path d="m4 16 8 4 8-4" />
      </svg>}
    </span>
    <strong>{name}</strong>
  </span>;
}
