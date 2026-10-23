import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrudPage, type CrudConfig } from "../components/CrudPage";
import { articlesConfig, resourcesConfig, scriptsConfig } from "../pages/entityConfigs";
import { databaseMeta } from "../components/DatabaseLabel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function CurrentLocation() {
  const location = useLocation();
  return <output aria-label="页面地址">{location.pathname}{location.search}</output>;
}

function show(config: CrudConfig, entry = "/") {
  vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(<MemoryRouter initialEntries={[entry]}><QueryClientProvider client={client}><CrudPage config={config} /><CurrentLocation /></QueryClientProvider></MemoryRouter>);
}

function list(items: object[], total = items.length) {
  return Response.json({ items, total, page: 1, page_size: 10, pages: Math.max(1, Math.ceil(total / 10)) });
}

describe("library classification and read-only preview", () => {
  it.each([articlesConfig, scriptsConfig, resourcesConfig])("$key keeps record metadata concise and preserves its file actions", async (config) => {
    const row = { id: 1, revision: 1, [config.columns[0].name]: "条目布局", [config.classification!.databaseField]: "Oracle", [config.classification!.categoryField!]: "安装部署", [config.fileLinks!.pathField]: "D:/docs/record.sql", version: 1, tags: "Oracle,ORACLE,安装部署,v1,RAC,RAC,ASM,备份,恢复" };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path.endsWith("facets") ? Response.json({ total: 1, items: [] }) : list([row])));
    show(config);
    await screen.findByText("条目布局", { exact: true });
    const record = within(screen.getByRole("list", { name: `${config.title}记录` })).getByRole("listitem");
    expect(record.querySelector(".database-label")).toHaveAttribute("title", "Oracle");
    expect([...record.querySelectorAll(".library-tag")].map((tag) => tag.textContent)).toEqual(["RAC", "ASM", "备份", "+1"]);
    expect(record.querySelector(".library-tag:last-child")).toHaveAttribute("title", "RAC、ASM、备份、恢复");
    expect(within(record).getByRole("button", { name: `${config.fileLinks!.openLabel}：条目布局` })).toBeEnabled();
    expect(within(record).getByRole("button", { name: "打开所在文件夹：条目布局" })).toBeEnabled();
    expect(within(record).getByRole("button", { name: "复制路径：条目布局" })).toBeEnabled();
    if (config.key !== "resources") {
      expect(record.querySelector(".library-record-path")).toHaveAttribute("title", "D:/docs/record.sql");
      expect(record.querySelector(".library-record-path")).toHaveTextContent("D:/docs/record.sql");
    }
  });

  it("keeps file preview controls compact and hides duplicate import descriptions", async () => {
    const row = { id: 19, revision: 1, title: "路径与预览布局", file_path: "D:/docs/完整文档路径.pdf", summary: "来自 其他/完整文档路径.pdf", wb_db: "MySQL", category: "技术文档", updated_at: "2026-10-23T20:30:45" };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("visual-preview")) return Response.json({ filename: "完整文档路径.pdf", viewer_url: "http://127.0.0.1:8012/onlinePreview?url=signed" });
      if (path === "/api/articles/19") return Response.json(row);
      return list([row]);
    }));
    show(articlesConfig);
    const record = await screen.findByRole("listitem");
    expect(record.querySelector(".library-record-path")).toHaveTextContent(row.file_path);
    expect(within(record).queryByText(row.summary)).not.toBeInTheDocument();
    fireEvent.click(within(record).getByRole("button", { name: "预览：路径与预览布局" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByTitle("原文件预览：完整文档路径.pdf");
    expect(preview.querySelector(".library-preview-overview .library-record-meta")).toHaveTextContent("MySQL");
    expect(preview.querySelector(".library-preview-overview .library-preview-meta")).toHaveTextContent("2026-10-23 20:30");
    const actions = within(preview).getByRole("region", { name: "快捷访问" });
    expect(within(actions).getByRole("button", { name: "打开文档：路径与预览布局" })).toBeEnabled();
    expect(within(actions).getByRole("button", { name: "打开所在文件夹：路径与预览布局" })).toHaveAttribute("title", row.file_path);
    expect(within(actions).getByRole("button", { name: "复制路径：路径与预览布局" })).toBeEnabled();
    expect(within(preview).queryByText(row.file_path)).not.toBeInTheDocument();
    expect(within(preview).queryByText(row.summary)).not.toBeInTheDocument();
  });

  it.each([articlesConfig, scriptsConfig, resourcesConfig])("$key restores classification from the URL and clears it without removing unrelated parameters", async (config) => {
    const classification = config.classification!;
    const category = "自定义分类 / 恢复&核验";
    const row = { id: 1, revision: 1, [config.columns[0].name]: "筛选记录", [classification.databaseField]: "Oracle", [classification.categoryField!]: category };
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [{ ...row, count: 1 }] });
      requests.push(path);
      return list([row]);
    }));
    const params = new URLSearchParams({ database: "Oracle", category, keep: "1" });
    show(config, `/${config.key}?${params}`);
    const active = await screen.findByRole("group", { name: "当前分类筛选" });
    expect(within(active).getByText("Oracle")).toBeInTheDocument();
    expect(within(active).getByText(category)).toBeInTheDocument();
    await waitFor(() => {
      const first = new URL(requests[0], "http://localhost").searchParams;
      expect(first.get(classification.databaseField)).toBe("Oracle");
      expect(first.get(classification.categoryField!)).toBe(category);
    });
    fireEvent.click(await screen.findByRole("combobox", { name: "筛选数据库" }));
    fireEvent.click(await screen.findByRole("option", { name: "MySQL（0）" }));
    let location = new URL(screen.getByLabelText("页面地址").textContent!, "http://localhost");
    expect(location.searchParams.get("database")).toBe("MySQL");
    expect(location.searchParams.has("category")).toBe(false);
    expect(location.searchParams.get("keep")).toBe("1");
    fireEvent.click(within(active).getByRole("button", { name: "清除分类" }));
    location = new URL(screen.getByLabelText("页面地址").textContent!, "http://localhost");
    expect(location.searchParams.has("database")).toBe(false);
    expect(location.searchParams.has("category")).toBe(false);
    expect(location.searchParams.get("keep")).toBe("1");
    expect(screen.queryByRole("group", { name: "当前分类筛选" })).not.toBeInTheDocument();
  });

  it.each([scriptsConfig])("$key previews linked files when the database body is empty without copying them into the editor", async (config) => {
    const row = { id: 12, revision: 2, title: "仅关联文件", content: "", file_path: "D:/docs/old.sql" };
    const reads: string[] = [];
    const fileBody = "SELECT '<img src=x onerror=alert(1)>'; -- 中文";
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      reads.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("visual-preview")) return Response.json({ detail: "内置查看器暂不可用" }, { status: 503 });
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

  it.each(["D:/docs/layout.pdf", ""])("articles show only source-file preview and preserve saved content when path is %s", async (filePath) => {
    const row = { id: 18, revision: 3, title: "仅源文件预览", content: "保留的历史文章正文", file_path: filePath };
    const reads: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      reads.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("visual-preview")) return Response.json({ detail: "内置查看器暂不可用" }, { status: 503 });
      if (path === "/api/articles/18") return Response.json(row);
      return list([row]);
    }));
    show(articlesConfig);
    fireEvent.click(await screen.findByRole("button", { name: "预览：仅源文件预览" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    await within(preview).findByText(filePath ? "原文件预览失败：内置查看器暂不可用" : "尚未关联源文件");
    expect(within(preview).queryByRole("region", { name: "正文预览" })).not.toBeInTheDocument();
    expect(within(preview).queryByText(row.content)).not.toBeInTheDocument();
    expect(reads).not.toContain("/api/articles/18/file-preview");
    fireEvent.click(within(preview).getByRole("button", { name: "编辑" }));
    expect(await within(screen.getByRole("dialog")).findByLabelText("正文", { exact: true })).toHaveValue(row.content);
  });

  it.each([articlesConfig, scriptsConfig])("$key embeds kkFileView for the original linked file without flattening its layout", async (config) => {
    const row = { id: 16, revision: 1, title: "原样预览", content: config.key === "articles" ? "不再展示的文章正文" : "", file_path: "D:/docs/layout.pdf" };
    const reads: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      reads.push(path);
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("visual-preview")) return Response.json({ filename: "layout.pdf", viewer: "kkFileView", viewer_version: "5.0.3", viewer_url: "http://127.0.0.1:8012/onlinePreview?url=signed" });
      if (path === `${config.path}16`) return Response.json(row);
      return list([row]);
    }));
    show(config);
    fireEvent.click(await screen.findByRole("button", { name: "预览：原样预览" }));
    const preview = screen.getByRole("complementary", { name: "记录预览" });
    const frame = await within(preview).findByTitle("原文件预览：layout.pdf");
    expect(frame).toHaveAttribute("src", "http://127.0.0.1:8012/onlinePreview?url=signed");
    expect(frame).toHaveAttribute("sandbox", expect.stringContaining("allow-scripts"));
    expect(within(preview).getByText("layout.pdf")).toHaveAttribute("title", "layout.pdf");
    expect(reads).not.toContain(`${config.path}16/file-preview`);
    if (config.key === "articles") expect(within(preview).queryByRole("region", { name: "正文预览" })).not.toBeInTheDocument();
  });

  it("shows file permission failures and retries without disabling file shortcuts", async () => {
    let denied = true;
    const row = { id: 13, revision: 1, title: "读取失败", content: "", file_path: "D:/docs/file.sql" };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path.endsWith("facets")) return Response.json({ total: 1, items: [] });
      if (path.endsWith("visual-preview")) return Response.json({ detail: "内置查看器暂不可用" }, { status: 503 });
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
    fireEvent.click(within(within(preview).getByRole("region", { name: "正文预览" })).getByRole("button", { name: "重试" }));
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
    await waitFor(() => expect(within(preview).getByRole("button", { name: "编辑" })).toBeEnabled());
    if (config.key === "scripts") expect(within(preview).getByText("完整正文，不能被摘要覆盖")).toBeInTheDocument();
    else expect(within(preview).queryByText("完整正文，不能被摘要覆盖")).not.toBeInTheDocument();
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
    const active = screen.getByRole("group", { name: "当前分类筛选" });
    expect(active.querySelector("img")).toHaveAttribute("src", databaseMeta.Oracle.icon);
    expect(active.querySelector(".active-classification-category")).toBeNull();
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
    expect(within(active).getByText("安装包")).toBeInTheDocument();
    fireEvent.click(within(active).getByRole("button", { name: "清除分类" }));
    await waitFor(() => {
      const params = new URL(requests.at(-1)!, "http://localhost").searchParams;
      expect(params.has("wb_db")).toBe(false);
      expect(params.has("kind")).toBe(false);
    });
    expect(screen.queryByRole("group", { name: "当前分类筛选" })).not.toBeInTheDocument();
    fireEvent.click(within(categories).getByRole("button", { name: /^自定义类型/ }));
    const categoryOnly = screen.getByRole("group", { name: "当前分类筛选" });
    expect(categoryOnly.querySelector(".database-label")).toBeNull();
    expect(within(categoryOnly).getByText("自定义类型")).toBeInTheDocument();
  });

  it("editing from source-only article preview preserves the full body and its revision", async () => {
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
    await within(preview).findByText("尚未关联源文件");
    expect(within(preview).queryByText(content)).not.toBeInTheDocument();
    expect(within(preview).queryByRole("region", { name: "正文预览" })).not.toBeInTheDocument();
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
