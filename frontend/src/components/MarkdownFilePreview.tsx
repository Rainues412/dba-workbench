import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import tocbot from "tocbot";
import { List, PanelLeftClose } from "lucide-react";
import DOMPurify from "dompurify";
import { ErrorState, LoadingState } from "./States";
import { createMarkdownParser } from "./markdownParser";

export function renderMarkdown(source: string, assetUrl: string) {
  const options = {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select"],
    FORBID_ATTR: ["style", "srcset"],
  };
  const parser = createMarkdownParser();
  const fragment = DOMPurify.sanitize(parser.parse(source, { gfm: true, async: false }), { ...options, RETURN_DOM_FRAGMENT: true });
  // Raw HTML headings also participate in the outline; never overwrite an author's id.
  for (const [index, heading] of [...fragment.querySelectorAll("h1,h2,h3,h4,h5,h6")].entries()) {
    if (!heading.id) heading.id = `preview-html-heading-${index}`;
  }
  for (const image of fragment.querySelectorAll("img")) {
    const reference = image.getAttribute("src");
    if (!reference || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) continue;
    const url = new URL(assetUrl, window.location.href);
    url.searchParams.set("path", reference);
    image.setAttribute("src", url.href);
  }
  for (const link of fragment.querySelectorAll("a")) {
    const href = link.getAttribute("href") || "";
    if (href.startsWith("#")) {
      try {
        const name = decodeURIComponent(href.slice(1));
        if (!fragment.getElementById(name) && fragment.getElementById(`preview-${name}`)) link.setAttribute("href", `#preview-${name}`);
      } catch { /* Malformed anchors stay inert when they do not match a heading. */ }
      continue;
    }
    if (!/^https?:\/\//i.test(href)) link.removeAttribute("href");
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  }
  // Sanitize again after URL adaptation so the inserted markup is the final checked result.
  return DOMPurify.sanitize(fragment, options);
}

export function MarkdownFilePreview({ filename, sourceUrl, assetUrl, expanded = false }: { filename: string; sourceUrl: string; assetUrl: string; expanded?: boolean }) {
  const scrollId = `markdown-${useId().replace(/[^a-z\d_-]/gi, "")}`;
  const documentRef = useRef<HTMLDivElement>(null);
  const tocRef = useRef<HTMLDivElement>(null);
  const [showToc, setShowToc] = useState(true);
  const [hasHeadings, setHasHeadings] = useState(false);
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
  useEffect(() => {
    if (!content.data || !documentRef.current || !tocRef.current) return;
    const document = documentRef.current;
    setHasHeadings(Boolean(document.querySelector("h1,h2,h3,h4,h5,h6")));
    tocbot.init({
      tocElement: tocRef.current, contentElement: document, scrollContainer: `#${scrollId}`,
      headingSelector: "h1,h2,h3,h4,h5,h6", collapseDepth: 6, orderedList: false,
      includeTitleTags: true, scrollSmooth: false, enableUrlHashUpdateOnScroll: false,
      headingsOffset: 16,
      onClick: (event) => {
        event.preventDefault();
        const id = (event.currentTarget as HTMLAnchorElement).hash.slice(1);
        const heading = [...document.querySelectorAll<HTMLElement>("[id]")].find((item) => item.id === decodeURIComponent(id));
        if (heading) document.scrollTo({ top: heading.offsetTop - 12 });
      },
    });
    return () => tocbot.destroy();
  }, [content.data, scrollId]);
  return content.isLoading ? <LoadingState label="正在读取 Markdown 源文件" />
    : content.error ? <ErrorState message={content.error.message} retry={() => void content.refetch()} />
    : <div className={`library-markdown-layout${expanded ? " expanded" : ""}${hasHeadings ? " has-outline" : ""}${showToc ? "" : " toc-collapsed"}`}>
      <nav className="library-toc" aria-label="文章目录" hidden={!hasHeadings || !showToc}>
        <div className="library-toc-heading"><strong><List size={16} />文章目录</strong><button className="icon-button" title="收起文章目录" aria-label="收起文章目录" onClick={() => setShowToc(false)}><PanelLeftClose size={16} /></button></div>
        <div ref={tocRef} />
      </nav>
      {hasHeadings && !showToc && <button className="button small library-toc-expand" onClick={() => setShowToc(true)}><List size={15} />展开目录</button>}
      <div id={scrollId} ref={documentRef} className="library-markdown" role="region" aria-label={`原文件预览：${filename}`} onClick={(event) => {
        const anchor = (event.target as Element).closest<HTMLAnchorElement>("a[href^='#']");
        if (!anchor) return;
        event.preventDefault();
        try {
          const id = decodeURIComponent(anchor.hash.slice(1));
          const heading = [...event.currentTarget.querySelectorAll<HTMLElement>("[id]")].find((item) => item.id === id);
          if (heading) event.currentTarget.scrollTo({ top: heading.offsetTop - 12 });
        } catch { /* Ignore malformed source-file anchors. */ }
      }} dangerouslySetInnerHTML={{ __html: content.data || "" }} />
    </div>;
}
