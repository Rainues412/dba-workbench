import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VaultBackupRestore } from "../components/VaultBackupRestore";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function show(onRestore = vi.fn().mockResolvedValue(undefined), onBackup = vi.fn().mockResolvedValue(undefined)) {
  render(<VaultBackupRestore canRestore={() => true} onBackup={onBackup} onRestore={onRestore} />);
  fireEvent.change(screen.getByLabelText("选择加密备份"), { target: { files: [new File(["{}"], "vault-test.json", { type: "application/json" })] } });
  return { onRestore, onBackup };
}

describe("vault backup restore confirmation", () => {
  it("keeps the overwrite consequence visible and never restores on selection or cancellation", () => {
    const { onRestore } = show();
    expect(screen.getByRole("dialog", { name: "恢复加密备份" })).toBeVisible();
    expect(screen.getByText("恢复会替换当前保险箱全部密文，现有条目将被备份内容覆盖。")).toBeVisible();
    expect(onRestore).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onRestore).not.toHaveBeenCalled();
  });

  it("retains the file after a failed restore and allows retry", async () => {
    const restore = vi.fn().mockRejectedValueOnce(new Error("恢复失败，请重试")).mockResolvedValueOnce(undefined);
    show(restore);
    fireEvent.click(screen.getByRole("button", { name: "确认恢复" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("恢复失败，请重试");
    expect(screen.getByTitle("vault-test.json")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认恢复" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(restore).toHaveBeenCalledTimes(2);
  });

  it("does not restore when backing up, and prevents closing during the pending operation", async () => {
    let finish = () => {};
    const backup = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const { onRestore } = show(undefined, backup);
    fireEvent.click(screen.getByRole("button", { name: "先备份当前保险箱" }));
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "处理中…" })).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    finish();
    expect(await screen.findByRole("status")).toHaveTextContent("当前保险箱备份已生成");
    expect(onRestore).not.toHaveBeenCalled();
  });
});
