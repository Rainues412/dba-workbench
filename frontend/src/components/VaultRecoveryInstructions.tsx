export function VaultRecoveryInstructions() {
  return <div className="recovery-instructions">
    <p>在工作台的 <code>server</code> 目录运行：</p>
    <pre className="vault-recovery-command">python -m backend.admin backup-recovery-key --output &lt;绝对备份目录&gt;</pre>
    <p>恢复私钥应与数据库分开保存。确认副本可读取后，再标记备份完成。</p>
  </div>;
}
