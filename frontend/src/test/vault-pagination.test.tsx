import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Vault } from "../pages/Vault";

const mocks = vi.hoisted(() => ({ encrypt: vi.fn(), decrypt: vi.fn(), unlock: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({ useAuth: () => ({ session: { user: { id: 1 }, reauthenticated_until: "2099-01-01T00:00:00Z" }, reauthenticate: vi.fn() }) }));
vi.mock("../vault/crypto", () => ({ encryptSecret: mocks.encrypt, decryptSecret: mocks.decrypt, unlockVault: mocks.unlock, createVaultProfile: vi.fn() }));

let requests: string[];
let updates: Array<Record<string, unknown>>;
let conflict: boolean;
let failSecondPage: boolean;
let deleted: Set<number>;
let deleteFailure: number | null;
const cipher = (id: number, revision = 1) => ({ id, item_key: `key-${id}`, revision, ciphertext: `cipher-${id}` });

beforeEach(() => {
  requests = []; updates = []; conflict = false; failSecondPage = false;
  deleted = new Set(); deleteFailure = null;
  mocks.unlock.mockResolvedValue(new Uint8Array(32));
  mocks.decrypt.mockImplementation(async (_key, item) => ({ site: `Site ${item.id}`, url: "", username: "user", password: "secret", category: "测试", notes: "", favorite: item.id === 201 }));
  mocks.encrypt.mockImplementation(async (_key, _user, secret, itemKey) => ({ item_key: itemKey, ciphertext: JSON.stringify(secret) }));
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    requests.push(path);
    if (path === "/api/vault/profile") return Response.json({ initialized: true, profile: { recovery_confirmed_at: "2026-01-01" } });
    if (path === "/api/vault/legacy/status") return Response.json({ backend_entries: 0 });
    if (path.startsWith("/api/vault/items?")) {
      const page = Number(new URL(path, "http://localhost").searchParams.get("page"));
      if (page === 2 && failSecondPage) return Response.json({}, { status: 500 });
      return Response.json({ items: (page === 1 ? Array.from({ length: 200 }, (_, index) => cipher(index + 1)) : [cipher(201, 2)]).filter((item) => !deleted.has(item.id)), total: 201 - deleted.size, page, pages: 2, has_next: page === 1 });
    }
    if (path.startsWith("/api/vault/items/") && init?.method === "DELETE") {
      const id = Number(path.split("/").pop()!.split("?")[0]);
      if (id === deleteFailure) return Response.json({}, { status: 409 });
      deleted.add(id); return Response.json({ ok: true });
    }
    if (path === "/api/vault/items/201" && init?.method === "PUT") {
      updates.push(JSON.parse(String(init.body)));
      if (conflict && updates.length === 1) return Response.json({}, { status: 409 });
      return Response.json({ ok: true });
    }
    throw new Error(`Unexpected request: ${path}`);
  }));
  vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.clearAllMocks(); });

async function unlock() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><Vault /></QueryClientProvider>);
  const input = await screen.findByLabelText("保险箱主密码");
  fireEvent.change(input, { target: { value: "long-master-password" } });
  fireEvent.submit(input.closest("form")!);
  await screen.findByText("保险箱已解锁");
}

describe("vault complete loading, pagination and favorites", () => {
  it("toggles a revealed password back to masked without affecting other cards", async () => {
    await unlock();
    const card = (await screen.findByRole("heading", { name: "Site 1" })).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "查看" }));
    expect(within(card).getByText("secret")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "隐藏" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(within(card).getByRole("button", { name: "隐藏" }));
    expect(within(card).queryByText("secret")).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "查看" })).toHaveAttribute("aria-pressed", "false");
  });

  it("cancels bulk deletion without sending requests, then deletes only selected revisions", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await unlock(); await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 Site 1" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 Site 2" }));
    fireEvent.click(screen.getByRole("button", { name: "删除所选" }));
    expect(deleted.size).toBe(0);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("2 条"));
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "删除所选" }));
    await screen.findByText("已删除 2 条密码");
    expect([...deleted]).toEqual([1, 2]);
    expect(requests).toContain("/api/vault/items/1?revision=1");
    expect(screen.queryByRole("heading", { name: "Site 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Site 3" })).toBeInTheDocument();
  });

  it("clears selection on page and filter changes and selects only the current page", async () => {
    await unlock(); await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前页" }));
    expect(screen.getByText("已选 20 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    expect(screen.getByText("已选 0 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前页" }));
    fireEvent.change(screen.getByRole("textbox", { name: "搜索保险箱" }), { target: { value: "Site 201" } });
    expect(screen.getByText("已选 0 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前页" }));
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();
  });

  it("stops bulk deletion on conflict and reports partial completion without force retry", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true); deleteFailure = 2;
    await unlock(); await screen.findByRole("heading", { name: "Site 1" });
    for (const id of [1, 2, 3]) fireEvent.click(screen.getByRole("checkbox", { name: `选择 Site ${id}` }));
    fireEvent.click(screen.getByRole("button", { name: "删除所选" }));
    await screen.findByText(/删除已暂停：已删除 1 条/);
    expect([...deleted]).toEqual([1]);
    expect(requests.filter((path) => path === "/api/vault/items/2?revision=1")).toHaveLength(1);
    expect(requests).not.toContain("/api/vault/items/3?revision=1");
    expect(screen.getByRole("heading", { name: "Site 2" })).toBeInTheDocument();
  });

  it("loads every cipher page and searches beyond the first 200 records", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    expect(requests).toContain("/api/vault/items?page=2&page_size=200");
    expect(screen.getByText("共 201 条")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Site 201" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "第 11 页" }));
    expect(screen.getByRole("heading", { name: "Site 201" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "搜索保险箱" }), { target: { value: "Site 201" } });
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第 1 页" })).toHaveAttribute("aria-current", "page");
  });

  it("filters favorites globally and preserves the favorite when editing", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("checkbox", { name: "仅收藏" }));
    expect(screen.getByRole("heading", { name: "Site 201" })).toBeInTheDocument();
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("checkbox", { name: "收藏此条目" })).toBeChecked();
    fireEvent.submit(within(dialog).getByLabelText("名称或备注").closest("form")!);
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(JSON.parse(String(updates[0].ciphertext)).favorite).toBe(true);
  });

  it("can remove a favorite and reloads all pages before retrying an edit conflict", async () => {
    conflict = true;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("checkbox", { name: "仅收藏" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "收藏此条目" }));
    fireEvent.submit(within(dialog).getByLabelText("名称或备注").closest("form")!);
    await waitFor(() => expect(updates).toHaveLength(2));
    expect(updates[1].revision).toBe(2);
    expect(JSON.parse(String(updates[1].ciphertext)).favorite).toBe(false);
    expect(requests.filter((path) => path === "/api/vault/items?page=2&page_size=200").length).toBeGreaterThanOrEqual(2);
  });

  it("does not display a partial list when a later cipher page fails", async () => {
    failSecondPage = true;
    await unlock();
    await screen.findByText("密文列表加载失败");
    expect(screen.queryByRole("heading", { name: "Site 1" })).not.toBeInTheDocument();
    expect(mocks.decrypt).not.toHaveBeenCalled();
  });

  it("zeros the active key and removes decrypted entries when locked", async () => {
    const key = new Uint8Array(32).fill(7);
    mocks.unlock.mockResolvedValue(key);
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("button", { name: "立即锁定" }));
    expect(screen.getByRole("heading", { name: "保险箱已锁定" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Site 1" })).not.toBeInTheDocument();
    expect(key.every((value) => value === 0)).toBe(true);
  });

  it("ignores a decryption failure that completes after the vault was locked", async () => {
    let rejectDecrypt!: (reason: Error) => void;
    mocks.decrypt.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectDecrypt = reject; }));
    await unlock();
    await waitFor(() => expect(mocks.decrypt).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "立即锁定" }));
    await act(async () => { rejectDecrypt(new Error("late decrypt error")); });
    expect(screen.getByRole("heading", { name: "保险箱已锁定" })).toBeInTheDocument();
    expect(screen.queryByText("密文校验失败，保险箱已锁定")).not.toBeInTheDocument();
  });
});
