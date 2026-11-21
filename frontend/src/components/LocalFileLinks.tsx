import { FileName } from "./FileName";
import { useState } from "react";
import { ExternalLink, FileCode2, FolderOpen } from "lucide-react";
import { api, ApiError, Entity, jsonBody } from "../api/client";
import { CopyFeedbackButton } from "./CopyFeedbackButton";

export type FileLinksConfig = {
  pathField: string;
  openMode: "edit" | "open";
  openLabel: string;
  urlField?: string;
};

export function LocalFileLinks({ row, label, config, disabled, onNotice, actionLabel, compact = false, inlineCopyFeedback = false }: {
  row: Entity;
  label: string;
  config: FileLinksConfig;
  disabled: boolean;
  onNotice: (message: string) => void;
  actionLabel?: string;
  compact?: boolean;
  inlineCopyFeedback?: boolean;
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

  return <span className={`record-links${compact ? " compact-file-links" : ""}`}>
    {href ? <a className="record-title-link" href={href} target="_blank" rel="noopener noreferrer" title={label} aria-label={`打开网址：${label}`}><span>{actionLabel ? "打开网址" : label}</span><ExternalLink size={14} /></a>
      : path ? <button className="record-title-link" type="button" title={label} disabled={disabled || busy} onClick={() => void open(config.openMode)} aria-label={`${config.openLabel}：${label}`}><span>{actionLabel || <FileName text={label} path={path} />}</span><FileCode2 size={14} /></button>
      : !actionLabel && <span>{label}</span>}
    {path && <span className="record-path-line">
      <button className="record-path-link" type="button" title={path} aria-label={`打开所在文件夹：${label}`} disabled={disabled || busy} onClick={() => void open("folder")}><FolderOpen size={13} /><span>{compact ? "所在文件夹" : path}</span></button>
      <CopyFeedbackButton value={path} className="record-copy-path" label="复制" accessibleLabel={`复制路径：${label}`} title="复制路径" disabled={disabled}
        showInline={inlineCopyFeedback} onCopied={() => onNotice(inlineCopyFeedback ? "" : "路径已复制")} onError={() => onNotice("复制失败，请手动复制文件路径")} />
    </span>}
    {url && !href && <small className="muted">网址无效，仅支持 http/https</small>}
  </span>;
}
