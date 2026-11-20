import { useState } from "react";
import { Minus, Plus } from "lucide-react";
import type { RecoveryQuestion } from "./desktopVault";

export function readRecoveryQuestions(form: FormData): RecoveryQuestion[] {
  const answers = form.getAll("recovery_answer");
  return form.getAll("recovery_question").map((question, index) => ({
    question: String(question).trim(),
    answer: String(answers[index] ?? "").trim(),
  }));
}

export function RecoveryQuestionFields() {
  const [ids, setIds] = useState([0]);
  const [nextId, setNextId] = useState(1);
  return <fieldset className="vault-question-fields">
    <legend>密保问题</legend>
    <p className="muted">重置主密码时需答对全部问题。</p>
    {ids.map((id, index) => <div key={id} className="vault-question">
      <label>问题 {index + 1}<input name="recovery_question" type="text" maxLength={200} autoComplete="off" required /></label>
      <label>答案 {index + 1}<input name="recovery_answer" type="password" maxLength={256} autoComplete="off" required /></label>
      {ids.length > 1 && <button type="button" className="button small" aria-label={`移除问题 ${index + 1}`} onClick={() => setIds(ids.filter((value) => value !== id))}><Minus size={14} />移除</button>}
    </div>)}
    {ids.length < 3 && <button type="button" className="button small" onClick={() => { setIds([...ids, nextId]); setNextId(nextId + 1); }}><Plus size={14} />添加问题</button>}
  </fieldset>;
}
