import { FormEvent, useState } from "react";
import { ArrowRight, Database, LockKeyhole, ShieldCheck } from "lucide-react";
import { ApiError } from "../api/client";
import { useAuth } from "./AuthContext";

export function AuthPage() {
  const { session, authenticate } = useAuth();
  const setup = Boolean(session?.setup_required);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "");
    if (setup && password !== String(data.get("confirm") ?? "")) {
      setError("两次输入的密码不一致");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await authenticate(setup ? "setup" : "login", String(data.get("username") ?? ""), password);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "操作失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-showcase" aria-hidden="true">
        <div className="auth-brand"><span className="brand-mark"><Database size={28} /></span><span><strong>DBA 工作台</strong><small>LOCAL OPERATIONS CONSOLE</small></span></div>
        <div className="auth-message"><span className="auth-orbit"><ShieldCheck size={34} /></span><p className="eyebrow">SECURE BY DEFAULT</p><h2>把日常 DBA 工作，<br />收拢到一个安全空间。</h2><p>脚本、知识、任务、客户与密码资产都保存在本机，并以明确的安全边界运行。</p></div>
        <div className="auth-features"><span><LockKeyhole size={17} />Argon2id 身份验证</span><span><ShieldCheck size={17} />客户端加密保险箱</span></div>
      </section>
      <section className="auth-panel">
        <div className="auth-card" aria-labelledby="auth-title">
          <div className="auth-mobile-brand"><span className="brand-mark small"><Database size={19} /></span><strong>DBA 工作台</strong></div>
          <p className="eyebrow">{setup ? "FIRST TIME SETUP" : "WELCOME BACK"}</p>
          <h1 id="auth-title">{setup ? "创建首位 Owner" : "登录 DBA 工作台"}</h1>
          <p className="muted auth-description">
            {setup ? "没有默认账号。请创建仅属于你的本机管理员账号。" : "输入本机 Owner 凭据，继续管理你的工作空间。"}
          </p>
          <form onSubmit={submit} className="stack auth-form">
            <label>用户名<input name="username" autoComplete="username" minLength={3} placeholder="输入用户名" required autoFocus /></label>
            <label>登录密码<input name="password" type="password" autoComplete={setup ? "new-password" : "current-password"} minLength={12} placeholder="至少 12 位" required /></label>
            {setup && <label>确认密码<input name="confirm" type="password" autoComplete="new-password" minLength={12} placeholder="再次输入密码" required /></label>}
            {error && <div className="alert error" role="alert">{error}</div>}
            <button className="button primary auth-submit" disabled={busy}>{busy ? "处理中…" : setup ? "创建并登录" : "登录"}{!busy && <ArrowRight size={18} />}</button>
          </form>
          <p className="auth-footnote"><ShieldCheck size={14} />仅允许从本机回环地址访问</p>
        </div>
      </section>
    </main>
  );
}
