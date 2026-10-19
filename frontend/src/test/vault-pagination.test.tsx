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
const cipher = (id: number, revision = 1) => ({ id, item_key: `key-${id}`, revision, ciphertext: `cipher-${id}` });

beforeEach(() => {
  requests = []; updates = []; conflict = false; failSecondPage = false;
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
      return Response.json({ items: page === 1 ? Array.from({ length: 200 }, (_, index) => cipher(index + 1)) : [cipher(201, 2)], total: 201, page, pages: 2, has_next: page === 1 });
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
    fireEvent.submit(within(dialog).getByLabelText("系统/网站").closest("form")!);
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
    fireEvent.submit(within(dialog).getByLabelText("系统/网站").closest("form")!);
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
