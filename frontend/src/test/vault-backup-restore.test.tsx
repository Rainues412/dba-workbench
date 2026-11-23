import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { VaultBackupRestore } from "../components/VaultBackupRestore";
import { openBackup, readBackupFile, readBackupIdentity } from "../vault/backup";

vi.mock("../api/client", () => ({
  api: vi.fn(),
  hasVaultAccessToken: () => true,
  setVaultAccessToken: vi.fn(),
  jsonBody: JSON.stringify,
  VAULT_LOCKED_EVENT: "dba:vault-locked",
}));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ session: { user: { id: 9 } } }) }));
vi.mock("../vault/backup", () => ({ readBackupFile: vi.fn(), openBackup: vi.fn(), readBackupIdentity: vi.fn() }));
vi.mock("../components/TaskStatusButton", async (original) => ({
  ...await original<typeof import("../components/TaskStatusButton")>(), useTaskStatusReducedMotion: () => true,
}));
vi.mock("../vault/crypto", () => ({
  unlockVault: vi.fn(async (_password, _user, _profile, authorize) => {
    await authorize("test-wrapping-key");
    return new Uint8Array(32);
  }),
  encryptSecret: vi.fn(async () => ({ ciphertext: "sample-ciphertext" })),
}));

const currentProfile = { wrapped_dek: "local-profile" };
const file = new File(["encrypted"], "vault-test.age");
const identity = new File(["identity"], "vault-key.txt");
const records = [{ site: "测试连接", username: "tester", category: "数据库", password: "test-only-secret" }];

function show(initialized = true, onOpenVault = vi.fn()) {
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === "/api/vault/backup-settings") return { interval_hours: 24, retention: 10, portable_ready: false, directory: "D:/data/vault-backups/9", key_directory: "D:/data/vault-backup-keys/9/portable" } as never;
    if (path === "/api/vault/backups/open-directory?kind=key") return undefined as never;
    if (path === "/api/vault/backups") return (options?.method === "POST" ? { filename: "backup-test.age" } : []) as never;
    if (path === "/api/vault/profile") return { initialized, profile: initialized ? currentProfile : null } as never;
    if (path === "/api/vault/backup/verify-master") return undefined as never;
    if (path === "/api/vault/backup") return { digest: "current-digest", items: [{}, {}], profile: currentProfile } as never;
    if (path === "/api/vault/backup/restore") return { item_count: 1, safety_backup: "protected.json" } as never;
    throw new Error("Unexpected request");
  });
  vi.mocked(readBackupFile).mockResolvedValue({ format: "dba-vault-backup-v3" } as never);
  vi.mocked(readBackupIdentity).mockResolvedValue("test-identity");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VaultBackupRestore desktop onOpenVault={onOpenVault} /></QueryClientProvider>);
}

async function submitFile() {
  await waitFor(() => expect(screen.getByRole("button", { name: "导入" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "导入" }));
  const dialog = await screen.findByRole("dialog", { name: "导入密码库备份" });
  expect(within(dialog).queryByLabelText("选择备份文件")).not.toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("当前密码库主密码"), { target: { value: "test-only-master" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "验证" }));
  fireEvent.change(await within(dialog).findByLabelText("选择备份文件"), { target: { files: [file] } });
  expect(within(dialog).getByRole("button", { name: "下一步" })).toBeDisabled();
  fireEvent.change(within(dialog).getByLabelText("选择备份恢复密钥"), { target: { files: [identity] } });
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "下一步" })).toBeEnabled());
  fireEvent.click(within(dialog).getByRole("button", { name: "下一步" }));
  return dialog;
}

function restoreCalls() {
  return vi.mocked(api).mock.calls.filter(([path]) => path === "/api/vault/backup/restore");
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("password vault backup settings", () => {
  it("creates a manual backup without a password prompt and reports success", async () => {
    show();
    const button = await screen.findByRole("button", { name: "手动备份" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText("备份创建成功")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api).toHaveBeenCalledWith("/api/vault/backups", { method: "POST" });
  });

  it("shows the interval and retention options and writes nothing before confirmation", async () => {
    show();
    expect(await screen.findByLabelText("自动备份间隔")).toHaveValue("24");
    const directory = screen.getByRole("group", { name: "备份存放目录" });
    expect(directory).toHaveTextContent("D:/data/vault-backups/9");
    expect(within(directory).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(directory).getByRole("button", { name: "打开备份目录" })).toBeEnabled();
    const keyDirectory = screen.getByRole("group", { name: "密钥存放目录" });
    expect(keyDirectory.parentElement).toBe(directory.parentElement);
    expect(keyDirectory).toHaveTextContent("D:/data/vault-backup-keys/9/portable");
    expect(within(keyDirectory).queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "另存恢复密钥" })).not.toBeInTheDocument();
    fireEvent.click(within(keyDirectory).getByRole("button", { name: "打开密钥目录" }));
    expect(api).toHaveBeenCalledWith("/api/vault/backups/open-directory?kind=key", { method: "POST" });
    expect(screen.getByLabelText("备份保留数量")).toHaveValue("10");
    vi.mocked(openBackup).mockResolvedValue(records as never);
    const review = await submitFile();
    expect(await within(review).findByRole("list", { name: "将导入的密码条目" })).toHaveTextContent("测试连接");
    expect(review).not.toHaveTextContent("test-only-secret");
    expect(review).toHaveTextContent("包含 1 条凭据");
    expect(review).toHaveTextContent("当前的 2 条凭据");
    expect(restoreCalls()).toHaveLength(0);
    expect(within(review).queryByRole("button", { name: "取消" })).not.toBeInTheDocument();
    fireEvent.click(within(review).getByRole("button", { name: "关闭备份对话框" }));
    expect(restoreCalls()).toHaveLength(0);
  });

  it("rejects a mismatched recovery key without allowing a restore", async () => {
    show();
    vi.mocked(openBackup).mockRejectedValue(new Error("备份恢复密钥不匹配"));
    const dialog = await submitFile();
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("备份恢复密钥不匹配");
    expect(within(dialog).queryByRole("button", { name: "导入" })).not.toBeInTheDocument();
    expect(restoreCalls()).toHaveLength(0);
  });

  it("submits the reviewed snapshot only after confirmation", async () => {
    show();
    vi.mocked(openBackup).mockResolvedValue(records as never);
    const dialog = await submitFile();
    fireEvent.click(await within(dialog).findByRole("button", { name: "导入" }));
    expect(await screen.findByText(/覆盖前的安全备份已保存/)).toBeVisible();
    expect(restoreCalls()).toHaveLength(1);
    expect(JSON.parse(String(restoreCalls()[0][1]?.body))).toEqual({
      confirm: "RESTORE", expected_digest: "current-digest", wrapping_key: "test-wrapping-key", items: [{ ciphertext: "sample-ciphertext" }],
    });
  });

  it("directs a new user to set their master password before import", async () => {
    const openVault = vi.fn();
    show(false, openVault);
    const button = await screen.findByRole("button", { name: "导入" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    const dialog = await screen.findByRole("dialog", { name: "导入密码库备份" });
    expect(within(dialog).queryByLabelText("选择备份文件")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "前往保险箱" }));
    expect(openVault).toHaveBeenCalledOnce();
  });
});
