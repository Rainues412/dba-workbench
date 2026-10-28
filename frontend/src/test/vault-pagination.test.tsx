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
    if (path === "/api/vault/captcha") return Response.json({ challenge_id: "a".repeat(32), image: "data:image/svg+xml;base64,PHN2Zy8+", expires_in: 180 });
    if (path === "/api/vault/profile/recover" && init?.method === "PUT") return Response.json({ updated_at: "2026-01-01" });
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
  it("reveals a new entry password without saving, preserves typed text and resets on reopening", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("button", { name: "新增条目" }));
    let dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText("密码");
    const username = within(dialog).getByLabelText("账号名");
    expect(username).toHaveValue("");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("type", "password");
    fireEvent.change(input, { target: { value: "test-only-entry-password" } });
    const toggle = within(dialog).getByRole("button", { name: "显示密码" });
    expect(toggle).toHaveAttribute("type", "button");
    expect(toggle).toHaveAttribute("aria-controls", input.id);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveValue("test-only-entry-password");
    expect(within(dialog).getByRole("button", { name: "隐藏密码" })).toHaveAttribute("aria-pressed", "true");
    expect(mocks.encrypt).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "隐藏密码" }));
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveValue("test-only-entry-password");
    fireEvent.click(within(dialog).getByRole("button", { name: "显示密码" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "新增条目" }));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("密码")).toHaveAttribute("type", "password");
    expect(within(dialog).getByLabelText("密码")).toHaveValue("");
    expect(within(dialog).getByLabelText("账号名")).toHaveValue("");
  });

  it("saves an edited visible password through encryption and reopens masked", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("button", { name: "仅看收藏" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText("密码");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveValue("secret");
    fireEvent.click(within(dialog).getByRole("button", { name: "显示密码" }));
    fireEvent.change(input, { target: { value: "test-only-updated-password" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(mocks.encrypt.mock.calls.at(-1)?.[2]).toMatchObject({ password: "test-only-updated-password", favorite: true });
    expect(updates[0].revision).toBe(2);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(within(screen.getByRole("dialog")).getByLabelText("密码")).toHaveAttribute("type", "password");
  });

  it("recovers the master password from the locked gate after login-password and captcha verification", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<QueryClientProvider client={client}><Vault /></QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "忘记密码" }));
    await screen.findByRole("img", { name: "本机验证码" });
    fireEvent.change(screen.getByLabelText("登录密码"), { target: { value: "LoginPass9!" } });
    fireEvent.change(screen.getByLabelText("新保险箱主密码"), { target: { value: "NewMaster9!" } });
    fireEvent.change(screen.getByLabelText("确认新主密码"), { target: { value: "NewMaster9!" } });
    fireEvent.change(screen.getByPlaceholderText("输入 5 位验证码"), { target: { value: "AAAAA" } });
    fireEvent.click(screen.getByRole("button", { name: "确认重置" }));
    await screen.findByText("保险箱主密码已重置，请使用新密码解锁");
    expect(requests).toContain("/api/vault/profile/recover");
    const recoverCall = vi.mocked(fetch).mock.calls.find(([path]) => path === "/api/vault/profile/recover");
    expect(JSON.parse(String(recoverCall?.[1]?.body))).toMatchObject({
      new_master_password: "NewMaster9!",
      login_password: "LoginPass9!",
      captcha_id: "a".repeat(32),
      captcha_code: "AAAAA",
    });
    expect(screen.getByRole("heading", { name: "保险箱已锁定" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "修改主密码" })).not.toBeInTheDocument();
  });

  it("sorts cards by name with natural case-insensitive ordering", async () => {
    for (let id = 4; id <= 201; id += 1) deleted.add(id);
    const names = new Map([[1, "zulu"], [2, "Alpha"], [3, "beta"]]);
    mocks.decrypt.mockImplementation(async (_key, item) => ({ site: names.get(item.id) ?? `Site ${item.id}`, url: "", username: "user", password: "secret", category: "测试", notes: "", favorite: false }));
    await unlock();
    await screen.findByRole("heading", { name: "Alpha" });
    expect(Array.from(document.querySelectorAll(".vault-card h3"), (heading) => heading.textContent)).toEqual(["Alpha", "beta", "zulu"]);
  });

  it("groups the complete vault by category and filters before pagination", async () => {
    for (let id = 5; id <= 201; id += 1) deleted.add(id);
    const categories = new Map([[1, "工作"], [2, "个人"], [3, " 工作 "], [4, ""]]);
    mocks.decrypt.mockImplementation(async (_key, item) => ({ site: `Site ${item.id}`, url: "", username: "user", password: "secret", category: categories.get(item.id) ?? "", notes: "", favorite: false }));
    await unlock();
    const groups = await screen.findByRole("group", { name: "保险箱分类分组" });
    expect(within(groups).getByRole("button", { name: "全部分类，4 条" })).toHaveAttribute("aria-pressed", "true");
    expect(within(groups).getByRole("button", { name: "工作，2 条" })).toBeInTheDocument();
    expect(within(groups).getByRole("button", { name: "个人，1 条" })).toBeInTheDocument();
    expect(within(groups).getByRole("button", { name: "未分类，1 条" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 Site 1" }));
    fireEvent.click(within(groups).getByRole("button", { name: "工作，2 条" }));
    expect(screen.getByRole("heading", { name: "Site 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Site 3" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Site 2" })).not.toBeInTheDocument();
    expect(screen.getByText("共 2 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除所选" })).toBeDisabled();
    fireEvent.click(within(groups).getByRole("button", { name: "未分类，1 条" }));
    expect(screen.getByRole("heading", { name: "Site 4" })).toBeInTheDocument();
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
  });

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
    const selectAll = screen.getByRole("checkbox", { name: "全选当前页" });
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 Site 1" }));
    expect(selectAll).not.toBeChecked();
    expect((selectAll as HTMLInputElement).indeterminate).toBe(true);
    expect(screen.getByText("已选 1 / 20 条").closest("label")).toHaveClass("has-selection");
    expect(screen.getByText("已选 1 / 20 条").closest("label")).not.toHaveClass("is-all-selected");
    fireEvent.click(selectAll);
    expect(selectAll).toBeChecked();
    expect((selectAll as HTMLInputElement).indeterminate).toBe(false);
    expect(screen.getByText("本页已全选 20 条").closest("label")).toHaveClass("is-all-selected");
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    expect(screen.getByText("全选当前页 20 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前页" }));
    fireEvent.change(screen.getByRole("textbox", { name: "按名称搜索保险箱" }), { target: { value: "Site 201" } });
    expect(screen.getByText("全选当前页 1 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前页" }));
    expect(screen.getByText("本页已全选 1 条")).toBeInTheDocument();
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

  it("loads every cipher page, places favorites first and searches globally", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    expect(requests).toContain("/api/vault/items?page=2&page_size=200");
    expect(screen.getByText("共 201 条")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Site 201" })).toBeInTheDocument();
    expect(document.querySelector(".vault-card h3")?.textContent).toBe("Site 201");
    fireEvent.click(screen.getByRole("button", { name: "第 11 页" }));
    expect(screen.getByRole("heading", { name: "Site 200" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "按名称搜索保险箱" }), { target: { value: "Site 201" } });
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第 1 页" })).toHaveAttribute("aria-current", "page");
    fireEvent.change(screen.getByRole("textbox", { name: "按名称搜索保险箱" }), { target: { value: "user" } });
    expect(screen.getByText("没有匹配的条目")).toBeInTheDocument();
  });

  it("filters favorites globally and preserves the favorite when editing", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("button", { name: "仅看收藏" }));
    expect(screen.getByRole("heading", { name: "Site 201" })).toBeInTheDocument();
    expect(screen.getByText("共 1 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("checkbox", { name: "收藏此条目" })).toBeChecked();
    fireEvent.submit(within(dialog).getByLabelText("名称或备注").closest("form")!);
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(JSON.parse(String(updates[0].ciphertext)).favorite).toBe(true);
  });

  it("toggles favorite directly from the card", async () => {
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.change(screen.getByRole("textbox", { name: "按名称搜索保险箱" }), { target: { value: "Site 201" } });
    const button = screen.getByRole("button", { name: "取消收藏 Site 201" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(button);
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(JSON.parse(String(updates[0].ciphertext)).favorite).toBe(false);
  });

  it("can remove a favorite and reloads all pages before retrying an edit conflict", async () => {
    conflict = true;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await unlock();
    await screen.findByRole("heading", { name: "Site 1" });
    fireEvent.click(screen.getByRole("button", { name: "仅看收藏" }));
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
