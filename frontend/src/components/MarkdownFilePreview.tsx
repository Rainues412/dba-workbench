import { useQuery } from "@tanstack/react-query";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { ErrorState, LoadingState } from "./States";

export function renderMarkdown(source: string, assetUrl: string) {
  const options = {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select"],
    FORBID_ATTR: ["style", "srcset"],
  };
  const fragment = DOMPurify.sanitize(marked.parse(source, { gfm: true, async: false }), { ...options, RETURN_DOM_FRAGMENT: true });
  for (const image of fragment.querySelectorAll("img")) {
    const reference = image.getAttribute("src");
    if (!reference || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) continue;
    const url = new URL(assetUrl, window.location.href);
    url.searchParams.set("path", reference);
    image.setAttribute("src", url.href);
  }
  for (const link of fragment.querySelectorAll("a")) {
    const href = link.getAttribute("href") || "";
    if (href.startsWith("#")) continue;
    if (!/^https?:\/\//i.test(href)) link.removeAttribute("href");
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  }
  // Sanitize again after URL adaptation so the inserted markup is the final checked result.
  return DOMPurify.sanitize(fragment, options);
}

export function MarkdownFilePreview({ filename, sourceUrl, assetUrl }: { filename: string; sourceUrl: string; assetUrl: string }) {
  const content = useQuery({
    queryKey: ["markdown-file", sourceUrl, assetUrl],
    queryFn: async ({ signal }) => {
      const response = await fetch(sourceUrl, { signal, credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error(`读取源文件失败（HTTP ${response.status}），请重新打开预览`);
      const bytes = await response.arrayBuffer();
      let source: string;
      try { source = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
      catch { source = new TextDecoder("gb18030").decode(bytes); }
      return renderMarkdown(source, assetUrl);
    },
    retry: false,
    gcTime: 0,
  });
  return content.isLoading ? <LoadingState label="正在读取 Markdown 源文件" />
    : content.error ? <ErrorState message={content.error.message} retry={() => void content.refetch()} />
    : <div className="library-markdown" role="region" aria-label={`原文件预览：${filename}`} dangerouslySetInnerHTML={{ __html: content.data || "" }} />;
}
