import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage, type CrudConfig } from "../components/CrudPage";
import { articlesConfig, resourcesConfig, scriptsConfig } from "../pages/entityConfigs";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function show(config: CrudConfig) {
  vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CrudPage config={config} /></QueryClientProvider></MemoryRouter>);
}

function list(items: object[], total = items.length) {
  return Response.json({ items, total, page: 1, page_size: 10, pages: Math.max(1, Math.ceil(total / 10)) });
}

describe("library classification and read-only preview", () => {
  it.each([articlesConfig, scriptsConfig])("$key previews linked files when the database body is empty without copying them into the editor", async (config) => {
    const row = { id: 12, revision: 2, title: "仅关联文件", content: "", file_path: "D:/docs/old.sql" };
    const reads: string[] = [];
    const fileBody = "SELECT '<img src=x onerror=alert(1)>'; -- 中文";
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      reads.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("file-preview")) return Response.json({ filename: "old.sql", content: fileBody, truncated: false });
      if (path === `${config.path}12`) return Response.json(row);
      return list([row]);
    }));
    show(config);
    fireEvent.click(await screen.findByRole("button", { name: "预览：仅关联文件" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText(fileBody);
    expect(within(preview).getByText(/预览来源：关联文件/)).toBeInTheDocument();
    expect(preview.querySelector("img")).toBeNull();
    expect(reads).toContain(`${config.path}12/file-preview`);
    fireEvent.click(within(preview).getByRole("button", { name: "编辑" }));
    const editor = await screen.findByRole("dialog");
    expect(within(editor).getByLabelText(config.key === "scripts" ? "脚本正文" : "正文", { exact: true })).toHaveValue("");
  });

  it("shows file permission failures and retries without disabling file shortcuts", async () => {
    let denied = true;
    const row = { id: 13, revision: 1, title: "读取失败", content: "", file_path: "D:/docs/file.sql" };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("file-preview")) return denied ? Response.json({ detail: "路径超出允许目录" }, { status: 403 }) : Response.json({ filename: "file.sql", content: "已恢复读取", truncated: true });
      if (path === "/api/scripts/13") return Response.json(row);
      return list([row]);
    }));
    show(scriptsConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：读取失败" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText("关联文件预览失败：路径超出允许目录");
    expect(within(preview).getByRole("button", { name: "打开脚本：读取失败" })).toBeEnabled();
    expect(within(preview).getByRole("button", { name: "复制正文" })).toBeDisabled();
    denied = false;
    fireEvent.click(within(preview).getByRole("button", { name: "重试" }));
    await within(preview).findByText("已恢复读取");
    expect(within(preview).getByRole("button", { name: "复制预览" })).toBeEnabled();
  });
  it("resources keep direct access and folder shortcuts without any preview entry", async () => {
    const reads: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      reads.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      return list([{ id: 1, revision: 1, name: "本地资源", path: "D:/test/resource.zip" }]);
    }));
    show(resourcesConfig);
    expect(await screen.findByRole("button", { name: "打开资源：本地资源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开所在文件夹：本地资源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制路径：本地资源" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "预览" })).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "记录预览" })).not.toBeInTheDocument();
    expect(reads).not.toContain("/api/resources/1");
  });
  it.each([articlesConfig, scriptsConfig])("$key loads detail on demand and keeps external file actions separate", async (config) => {
    const titleField = config.columns[0].name;
    const row = { id: 7, revision: 4, [titleField]: "快速访问测试", [config.fileLinks!.pathField]: "D:/test/record.sql", wb_db: "Oracle", db_type: "Oracle" };
    const requests: Array<{ path: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      requests.push({ path, init });
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path === `${config.path}7`) return Response.json({ ...row, content: "完整正文，不能被摘要覆盖", notes: "完整资源说明" });
      if (path === "/api/launcher/path") return Response.json({ ok: true });
      return list([row]);
    }));
    show(config);
    const previewButton = await screen.findByRole("button", { name: "预览：快速访问测试" });
    expect(requests.some(({ path }) => path === `${config.path}7`)).toBe(false);
    fireEvent.click(previewButton);
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText(config.key === "resources" ? "完整资源说明" : "完整正文，不能被摘要覆盖");
    expect(preview.querySelector("form")).toBeNull();
    expect(requests.some(({ init }) => init?.method)).toBe(false);
    fireEvent.click(within(preview).getByRole("button", { name: `打开所在文件夹：快速访问测试` }));
    await waitFor(() => expect(requests.find(({ path }) => path === "/api/launcher/path")).toBeTruthy());
    const launched = requests.find(({ path }) => path === "/api/launcher/path")!;
    expect(JSON.parse(String(launched.init?.body))).toEqual({ path: "D:/test/record.sql", mode: "folder" });
    expect(within(preview).getByRole("button", { name: `${config.fileLinks!.openLabel}：快速访问测试` })).toBeInTheDocument();
    expect(within(preview).getByRole("button", { name: "复制路径：快速访问测试" })).toBeInTheDocument();
    fireEvent.click(within(preview).getByRole("button", { name: "关闭预览" }));
    expect(screen.queryByRole("complementary", { name: "记录预览" })).not.toBeInTheDocument();
  });

  it.each([404, 500])("detail HTTP %s is retryable and never enables editing a partial record", async (status) => {
    let failing = true;
    const row = { id: 2, revision: 8, title: "详情失败测试" };
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method) writes.push(init);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path === "/api/scripts/2") return failing ? Response.json({}, { status }) : Response.json({ ...row, content: "成功读取正文" });
      return list([row]);
    }));
    show(scriptsConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：详情失败测试" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText("预览加载失败，请重试");
    expect(within(preview).getByRole("button", { name: "编辑" })).toBeDisabled();
    expect(writes).toHaveLength(0);
    failing = false;
    fireEvent.click(within(preview).getByRole("button", { name: "重试" }));
    await within(preview).findByText("成功读取正文");
    expect(within(preview).getByRole("button", { name: "编辑" })).not.toBeDisabled();
  });

  it("ignores an old detail response after selecting another record", async () => {
    const pending = new Map<string, (value: Response) => void>();
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path.endsWith("facets")) return Promise.resolve(Response.json({ total: 2, items: [] }));
      if (/\/api\/scripts\/\d+$/.test(path)) return new Promise<Response>((resolve) => pending.set(path, resolve));
      return Promise.resolve(list([{ id: 1, revision: 1, title: "第一条" }, { id: 2, revision: 1, title: "第二条" }]));
    }));
    show(scriptsConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：第一条" }));
    await waitFor(() => expect(pending.has("/api/scripts/1")).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "预览：第二条" }));
    await waitFor(() => expect(pending.has("/api/scripts/2")).toBe(true));
    pending.get("/api/scripts/2")!(Response.json({ id: 2, revision: 1, title: "第二条", content: "当前选中的正文" }));
    await screen.findByText("当前选中的正文");
    pending.get("/api/scripts/1")!(Response.json({ id: 1, revision: 1, title: "第一条", content: "迟到的旧正文" }));
    await waitFor(() => expect(screen.queryByText("迟到的旧正文")).not.toBeInTheDocument());
    expect(screen.getByText("当前选中的正文")).toBeInTheDocument();
  });

  it("filters resources by kind and preserves custom category/database options across pages", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      requests.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 31, items: [
        { wb_db: "Oracle", kind: "安装包", count: 20 }, { wb_db: "达梦", kind: "自定义类型", count: 11 },
      ] });
      return list([{ id: 1, revision: 1, name: "资源" }], 31);
    }));
    show(resourcesConfig);
    fireEvent.click(await screen.findByRole("combobox", { name: "筛选数据库" }));
    fireEvent.click(await screen.findByRole("option", { name: "Oracle（20）" }));
    fireEvent.click(screen.getByRole("combobox", { name: "筛选数据库" }));
    expect(screen.getByRole("option", { name: "达梦（11）" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "筛选数据库" }), { key: "Escape" });
    const categories = screen.getByRole("group", { name: "资源类型" });
    expect(within(categories).getByRole("button", { name: /自定义类型/ })).toBeInTheDocument();
    fireEvent.click(within(categories).getByRole("button", { name: /^安装包/ }));
    await waitFor(() => {
      const params = new URL(requests.at(-1)!, "http://localhost").searchParams;
      expect(params.get("kind")).toBe("安装包");
      expect(params.get("wb_db")).toBe("Oracle");
      expect(params.get("page")).toBe("1");
    });
  });

  it("editing from preview saves the full body with its revision, and HTML stays text", async () => {
    const row = { id: 9, revision: 6, title: "完整记录", summary: "列表摘要" };
    const content = '<img src=x onerror="window.hacked=1">完整正文';
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "PUT") { writes.push(init); return Response.json({ ...row, content, revision: 7 }); }
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path === "/api/articles/9") return Response.json({ ...row, content });
      return list([row]);
    }));
    show(articlesConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：完整记录" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText(content);
    expect(preview.querySelector(".library-article-body img")).toBeNull();
    fireEvent.click(within(preview).getByRole("button", { name: "编辑" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("正文", { exact: true })).toHaveValue(content);
    fireEvent.change(within(dialog).getByLabelText("标题", { exact: true }), { target: { value: "已修改标题" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(new Headers(writes[0].headers).get("If-Match")).toBe("6");
    expect(JSON.parse(String(writes[0].body))).toMatchObject({ title: "已修改标题", content });
  });

  it("preview history is read-only and cannot restore or write a version", async () => {
    const row = { id: 4, revision: 2, title: "脚本历史", version: 2 };
    const writes: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method) writes.push(init);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("/versions/1")) return Response.json({ content: "SELECT 'history';" });
      if (path === "/api/scripts/4") return Response.json({ ...row, content: "SELECT 'current';", versions: [{ version: 1, created_at: "2026-01-01" }] });
      return list([row]);
    }));
    show(scriptsConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：脚本历史" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText("SELECT 'current';");
    fireEvent.click(within(preview).getByText("历史版本", { selector: "summary" }));
    fireEvent.change(within(preview).getByLabelText("查看历史版本"), { target: { value: "1" } });
    expect(await within(preview).findByLabelText("历史正文")).toHaveValue("SELECT 'history';");
    expect(within(preview).queryByRole("button", { name: "恢复此版本为当前正文" })).not.toBeInTheDocument();
    expect(writes).toHaveLength(0);
  });
});
