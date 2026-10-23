import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkdownFilePreview, renderMarkdown } from "../components/MarkdownFilePreview";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MarkdownFilePreview filename="安装.md" sourceUrl="/preview-file/token/安装.md" assetUrl="/preview-file/assets/token" /></QueryClientProvider>);
}

describe("source Markdown rendering", () => {
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
