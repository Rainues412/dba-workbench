import { useLayoutEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

export function CopyFeedbackButton({ value, label, className, accessibleLabel, title, disabled, successLabel = "已复制", showInline = true, onCopied, onError }: {
  value: string;
  label: string;
  className: string;
  accessibleLabel?: string;
  title?: string;
  disabled?: boolean;
  successLabel?: string;
  showInline?: boolean;
  onCopied?: () => void;
  onError: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const request = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  useLayoutEffect(() => {
    setCopied(false);
    return () => {
      request.current++;
      window.clearTimeout(timer.current);
    };
  }, [value]);

  async function copy() {
    const attempt = ++request.current;
    window.clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      if (attempt !== request.current) return;
      setCopied(false);
      onError();
      return;
    }
    if (attempt !== request.current) return;
    onCopied?.();
    if (!showInline) return;
    setCopied(true);
    timer.current = window.setTimeout(() => setCopied(false), 1500);
  }

  return <>
    <button type="button" className={className} aria-label={accessibleLabel ?? label} title={title} disabled={disabled} onClick={() => void copy()}>
      <span className="copy-feedback-labels" data-copied={copied || undefined} aria-hidden="true">
        <span><Copy size={14} />{label}</span>
        {showInline && <span className="copy-feedback-success"><Check size={14} />{successLabel}</span>}
      </span>
    </button>
    {showInline && <span className="sr-only" role="status">{copied ? successLabel : ""}</span>}
  </>;
}
