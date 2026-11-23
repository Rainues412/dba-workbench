import { useEffect } from "react";
import { Check } from "lucide-react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";

export type VaultImportStep = 1 | 2 | 3;
const steps = ["验证主密码", "选择文件", "导入"];

export function VaultImportSteps({ step, complete, reduced }: { step: VaultImportStep; complete: boolean; reduced: boolean }) {
  return <ol className="vault-import-steps" aria-label="导入步骤" data-reduced={reduced || undefined}>
    {steps.map((label, index) => {
      const position = index + 1;
      const done = position < step || complete;
      return <li key={label} data-state={done ? "done" : position === step ? "active" : "waiting"}
        aria-current={position === step ? "step" : undefined}>
        <span className="vault-import-dot" aria-hidden="true">{done ? <Check size={15} /> : position}</span>
        <span className="vault-import-step-label">{label}</span>
      </li>;
    })}
  </ol>;
}

export function VaultImportProgress({ target, complete, reduced, onReachedEnd }: {
  target: number; complete: boolean; reduced: boolean; onReachedEnd: () => void;
}) {
  const progress = useMotionValue(0);
  const path = useTransform(progress, [0, 100], [0, 1]);
  const percent = useTransform(progress, (value) => `${Math.floor(value)}%`);

  useEffect(() => {
    if (reduced) {
      progress.set(target);
      if (target === 100) onReachedEnd();
      return;
    }
    const animation = animate(progress, target, {
      duration: target === 100 ? 0.43 : 0.31, ease: "easeOut",
      onComplete: () => { if (target === 100) onReachedEnd(); },
    });
    return () => animation.stop();
  }, [target, reduced, progress, onReachedEnd]);

  return <div className="vault-import-progress" role="status" aria-label={complete ? "导入完成" : "正在导入"} data-complete={complete || undefined} data-reduced={reduced || undefined}>
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="27" />
      <motion.circle cx="32" cy="32" r="27" pathLength={path} transform="rotate(-90 32 32)" />
    </svg>
    {complete ? <Check size={25} aria-hidden="true" /> : <motion.span aria-hidden="true">{percent}</motion.span>}
  </div>;
}
