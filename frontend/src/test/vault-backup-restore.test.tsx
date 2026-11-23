import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { VaultBackupRestore } from "../components/VaultBackupRestore";
import { openBackup, readBackupFile } from "../vault/backup";

vi.mock("../api/client", () => ({
  api: vi.fn(),
  hasVaultAccessToken: () => true,
  setVaultAccessToken: vi.fn(),
  jsonBody: JSON.stringify,
  VAULT_LOCKED_EVENT: "dba:vault-locked",
}));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ session: { user: { id: 9 } } }) }));
vi.mock("../vault/backup", () => ({ readBackupFile: vi.fn(), openBackup: vi.fn() }));
vi.mock("../vault/crypto", () => ({
  unlockVault: vi.fn(async () => new Uint8Array(32)),
  encryptSecret: vi.fn(async () => ({ ciphertext: "sample-ciphertext" })),
}));

const currentProfile = { wrapped_dek: "local-profile" };
const file = new File(["{}"], "vault-test.json", { type: "application/json" });

function show() {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/vault/backup-settings") return { interval_hours: 24, retention: 10, portable_ready: false } as never;
    if (path === "/api/vault/backups") return [] as never;
    if (path === "/api/vault/profile") return { initialized: true, profile: currentProfile } as never;
    if (path === "/api/vault/backup") return { digest: "current-digest", items: [{}, {}], profile: currentProfile } as never;
    if (path === "/api/vault/backup/restore") return { item_count: 1, safety_backup: "protected.json" } as never;
    throw new Error("Unexpected request");
  });
  vi.mocked(readBackupFile).mockResolvedValue({ format: "dba-vault-backup-v2" } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VaultBackupRestore desktop /></QueryClientProvider>);
}

async function submitFile() {
  await waitFor(() => expect(screen.getByRole("button", { name: "导入备份文件" })).toBeEnabled());
  fireEvent.change(screen.getByLabelText("选择密码库备份文件"), { target: { files: [file] } });
  const dialog = await screen.findByRole("dialog", { name: "校验密码库备份" });
  fireEvent.change(within(dialog).getByLabelText("备份密码"), { target: { value: "test-only-backup" } });
  fireEvent.change(within(dialog).getByLabelText("当前密码库主密码"), { target: { value: "test-only-master" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "校验备份" }));
}

function restoreCalls() {
  return vi.mocked(api).mock.calls.filter(([path]) => path === "/api/vault/backup/restore");
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("password vault backup settings", () => {
  it("shows the interval and retention options and writes nothing before confirmation", async () => {
    show();
    expect(await screen.findByLabelText("自动备份间隔")).toHaveValue("24");
    expect(screen.getByLabelText("备份保留数量")).toHaveValue("10");
    vi.mocked(openBackup).mockResolvedValue([{}] as never);
    await submitFile();
    const review = await screen.findByRole("dialog", { name: "确认恢复密码库" });
    expect(review).toHaveTextContent("包含 1 条凭据");
    expect(review).toHaveTextContent("当前的 2 条凭据");
    expect(restoreCalls()).toHaveLength(0);
    fireEvent.click(within(review).getByRole("button", { name: "取消" }));
    expect(restoreCalls()).toHaveLength(0);
  });

  it("rejects a wrong backup password without allowing a restore", async () => {
    show();
    vi.mocked(openBackup).mockRejectedValue(new Error("备份密码不正确"));
    await submitFile();
    expect(await screen.findByRole("alert")).toHaveTextContent("备份密码不正确");
    expect(screen.queryByRole("button", { name: "确认恢复" })).not.toBeInTheDocument();
    expect(restoreCalls()).toHaveLength(0);
  });

  it("submits the reviewed snapshot only after confirmation", async () => {
    show();
    vi.mocked(openBackup).mockResolvedValue([{}] as never);
    await submitFile();
    fireEvent.click(await screen.findByRole("button", { name: "确认恢复" }));
    expect(await screen.findByText(/覆盖前的安全备份已保存/)).toBeVisible();
    expect(restoreCalls()).toHaveLength(1);
    expect(JSON.parse(String(restoreCalls()[0][1]?.body))).toEqual({
      confirm: "RESTORE", expected_digest: "current-digest", items: [{ ciphertext: "sample-ciphertext" }],
    });
  });
});
