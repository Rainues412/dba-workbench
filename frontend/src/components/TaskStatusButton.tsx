import { CheckCircle2, Undo2 } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { usePreference } from "../preferences";

export type TaskStatusPhase = "pending" | "success";

export function useTaskStatusReducedMotion() {
  const systemReducedMotion = useReducedMotion();
  return usePreference("reduceMotion") === "true" || !!systemReducedMotion;
}

function wait(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

export async function playTaskStatusFeedback(request: Promise<unknown>, reducedMotion: boolean, showSuccess: () => void) {
  await Promise.all([request, reducedMotion ? undefined : wait(240)]);
  showSuccess();
  if (!reducedMotion) await wait(500);
}

export function TaskStatusButton({ completed = false, phase, disabled, accessibleLabel, title, onClick }: {
  completed?: boolean;
  phase?: TaskStatusPhase;
  disabled?: boolean;
  accessibleLabel?: string;
  title?: string;
  onClick: (trigger: HTMLButtonElement) => void;
}) {
  const label = completed ? "恢复" : "完成";
  const feedback = phase === "pending" ? "处理中…" : phase === "success" ? completed ? "任务已恢复" : "任务已完成" : "";
  return <SubmitMorph phase={phase} disabled={disabled} accessibleLabel={accessibleLabel ?? label} title={title}
    feedback={feedback} onClick={onClick}>
    {completed ? <Undo2 size={14} /> : <CheckCircle2 size={14} />}{label}
  </SubmitMorph>;
}

export function SubmitMorph({ phase, disabled, accessibleLabel, title, onClick, feedback, children, submit }: {
  phase?: TaskStatusPhase;
  disabled?: boolean;
  accessibleLabel: string;
  title?: string;
  onClick?: (trigger: HTMLButtonElement) => void;
  feedback: string;
  children: React.ReactNode;
  submit?: boolean;
}) {
  return <span className="task-morph-slot">
    <button className="button small task-morph" type={submit ? "submit" : "button"} data-phase={phase}
      aria-label={accessibleLabel} title={title} aria-disabled={phase ? true : undefined} disabled={disabled}
      onClick={(event) => { if (phase) event.preventDefault(); else onClick?.(event.currentTarget); }}>
      <span className="task-morph-label" aria-hidden="true">{children}</span>
      {phase === "pending" && <span className="task-morph-spinner" aria-hidden="true" />}
      {phase === "success" && <svg className="task-morph-check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" pathLength="1" /></svg>}
    </button>
    <span className="sr-only" role="status">{feedback}</span>
  </span>;
}
