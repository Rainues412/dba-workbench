import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkdownFilePreview, renderMarkdown } from "../components/MarkdownFilePreview";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(expanded = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MarkdownFilePreview filename="安装.md" sourceUrl="/preview-file/token/安装.md" assetUrl="/preview-file/assets/token" expanded={expanded} /></QueryClientProvider>);
}

describe("source Markdown rendering", () => {
  it("consumes standalone Typora TOC markers but preserves literal examples and links", () => {
    const element = document.createElement("div");
    element.innerHTML = renderMarkdown("[TOC]\n\n# 标题\n\n[toc]\n\n正文中的 [TOC] 保留。\n\n`[TOC]`\n\n```text\n[TOC]\n```\n\n[TOC](https://example.test/toc)", "/preview-file/assets/token");
    expect([...element.querySelectorAll("p")].some((paragraph) => paragraph.childElementCount === 0 && /^\[toc\]$/i.test(paragraph.textContent || ""))).toBe(false);
    expect(element.querySelector("h1")).toHaveTextContent("标题");
    expect(element).toHaveTextContent("正文中的 [TOC] 保留。");
    expect(element.querySelectorAll("code")).toHaveLength(2);
    for (const code of element.querySelectorAll("code")) expect(code).toHaveTextContent("[TOC]");
    expect(element.querySelector("a")).toHaveAttribute("href", "https://example.test/toc");
  });

  it("uses Tocbot for nested navigation without changing the page URL", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("# 安装\n\n## 检查\n\n### 执行")));
    show(true);
    const preview = await screen.findByRole("region", { name: "原文件预览：安装.md" });
    const toc = screen.getByRole("navigation", { name: "文章目录" });
    const jump = await within(toc).findByRole("link", { name: "执行" });
    expect(within(toc).getAllByRole("link")).toHaveLength(3);
    expect(jump.closest("ul")?.parentElement?.tagName).toBe("LI");
    const scroll = vi.fn();
    preview.scrollTo = scroll;
    const url = window.location.href;
    fireEvent.click(jump);
    expect(scroll).toHaveBeenCalledWith({ top: expect.any(Number) });
    expect(window.location.href).toBe(url);
    fireEvent.click(within(toc).getByRole("button", { name: "收起文章目录" }));
    expect(screen.queryByRole("navigation", { name: "文章目录" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开目录" }));
    expect(screen.getByRole("navigation", { name: "文章目录" })).toBeInTheDocument();
  });

  it("does not reserve an outline or show its toggle for a file without headings", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("只有正文，没有标题。")));
    show(true);
    expect(await screen.findByText("只有正文，没有标题。")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "文章目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "展开目录" })).not.toBeInTheDocument();
  });

  it("creates unique Chinese heading anchors with the official Marked extension and keeps source links usable", () => {
    const element = document.createElement("div");
    element.innerHTML = renderMarkdown("# 安装步骤\n\n## 安装步骤\n\n## 安装步骤\n\n[跳转](#安装步骤)\n\n<h3>HTML 标题</h3>", "/preview-file/assets/token");
    expect([...element.querySelectorAll("h1,h2")].map((heading) => heading.id)).toEqual(["preview-安装步骤", "preview-安装步骤-1", "preview-安装步骤-2"]);
    expect(element.querySelector("a")).toHaveAttribute("href", "#preview-安装步骤");
    expect(element.querySelector("h3")?.id).toBeTruthy();
  });

  it("renders GFM and HTML tables and adapts both Markdown and Typora HTML image references", () => {
    const html = renderMarkdown("| 数据库 | 版本 |\n| :--- | ---: |\n| Oracle | 11g |\n\n<table><tr><td>原始表格</td></tr></table>\n\n![原图](img/中文%20图片.png)\n\n<img src=\"img/typora.png\" width=\"200\">", "/preview-file/assets/token");
    const element = document.createElement("div");
    element.innerHTML = html;
    expect(element.querySelectorAll("table")).toHaveLength(2);
    expect(element.querySelector("tbody td")).toHaveTextContent("Oracle");
    expect(element.querySelector("td[align=right]")).toHaveTextContent("11g");
    const images = [...element.querySelectorAll("img")];
    expect(decodeURIComponent(new URL(images[0].src).searchParams.get("path")!)).toBe("img/中文 图片.png");
    expect(new URL(images[1].src).searchParams.get("path")).toBe("img/typora.png");
    expect(images[1]).toHaveAttribute("width", "200");
  });

  it("removes active markup while preserving code and safe external links", () => {
    const html = renderMarkdown('<script>window.hacked=1</script><img src="img/a.png" onerror="window.hacked=1"><iframe src="/api/export"></iframe><form action="/api/articles"><button>写入</button></form>\n\n[危险](javascript:alert(1)) [说明](https://example.test/docs)\n\n```html\n<img onerror="alert(1)">\n```', "/preview-file/assets/token");
    const element = document.createElement("div");
    element.innerHTML = html;
    expect(element.querySelector("script, iframe, form, button, [onerror]")).toBeNull();
    expect(element.querySelector("a[href^=javascript]")).toBeNull();
    expect(element.querySelector("pre code")).toHaveTextContent('<img onerror="alert(1)">');
    expect(element.querySelector("a[href^=https]")).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("loads the source file with an explicit loading state and displays its actual images and table", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("# 安装步骤\n\n![原图](img/setup.png)\n\n| 名称 |\n| --- |\n| Oracle |")));
    show();
    expect(screen.getByText("正在读取 Markdown 源文件")).toBeInTheDocument();
    const preview = await screen.findByRole("region", { name: "原文件预览：安装.md" });
    expect(within(preview).getByRole("table")).toHaveTextContent("Oracle");
    expect(within(preview).getByRole("img", { name: "原图" })).toHaveAttribute("src", expect.stringContaining("/preview-file/assets/token?path="));
  });

  it("makes expired or denied source reads retryable", async () => {
    let denied = true;
    vi.stubGlobal("fetch", vi.fn(async () => denied ? new Response("", { status: 404 }) : new Response("# 已恢复")));
    show();
    await screen.findByText("读取源文件失败（HTTP 404），请重新打开预览");
    denied = false;
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByRole("heading", { name: "已恢复" })).toBeInTheDocument();
  });
});
