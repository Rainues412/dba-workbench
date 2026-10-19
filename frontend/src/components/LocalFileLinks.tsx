import { useState } from "react";
import { Copy, ExternalLink, FileCode2, FolderOpen } from "lucide-react";
import { api, ApiError, Entity, jsonBody } from "../api/client";

export type FileLinksConfig = {
  pathField: string;
  openMode: "edit" | "open";
  openLabel: string;
  urlField?: string;
};

export function LocalFileLinks({ row, label, config, disabled, onNotice }: {
  row: Entity;
  label: string;
  config: FileLinksConfig;
  disabled: boolean;
  onNotice: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const path = String(row[config.pathField] ?? "").trim();
  const url = config.urlField ? String(row[config.urlField] ?? "").trim() : "";
  let href = "";
  try {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol)) href = parsed.href;
  } catch { /* Local file paths are handled by the authenticated launcher API. */ }

  async function open(mode: "edit" | "open" | "folder") {
    setBusy(true);
    try {
      await api("/api/launcher/path", { method: "POST", body: jsonBody({ path, mode }) });
      onNotice(mode === "folder" ? "已打开所在文件夹" : `已${config.openLabel}：${label}`);
    } catch (error) {
      onNotice(error instanceof ApiError ? error.message : "打开失败，请检查文件路径及本机服务状态");
    } finally {
      setBusy(false);
    }
  }

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(path);
      onNotice("路径已复制");
    } catch {
      onNotice("复制失败，请手动复制文件路径");
    }
  }

  return <span className="record-links">
    {href ? <a className="record-title-link" href={href} target="_blank" rel="noopener noreferrer" aria-label={`打开网址：${label}`}><span>{label}</span><ExternalLink size={14} /></a>
      : path ? <button className="record-title-link" type="button" disabled={disabled || busy} onClick={() => void open(config.openMode)} aria-label={`${config.openLabel}：${label}`}><span>{label}</span><FileCode2 size={14} /></button>
      : <span>{label}</span>}
    {path && <span className="record-path-line">
      <button className="record-path-link" type="button" title={path} aria-label={`打开所在文件夹：${label}`} disabled={disabled || busy} onClick={() => void open("folder")}><FolderOpen size={13} /><span>{path}</span></button>
      <button className="record-copy-path" type="button" aria-label={`复制路径：${label}`} title="复制路径" disabled={disabled} onClick={() => void copyPath()}><Copy size={12} />复制</button>
    </span>}
    {url && !href && <small className="muted">网址无效，仅支持 http/https</small>}
  </span>;
}
