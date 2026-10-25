import Highlighter from "react-highlight-words";

export function SearchHighlight({ text, query }: { text: string; query: string }) {
  // Keep ASCII word starts consistent with the server's title_matches rule.
  const terms = query.trim().split(/\s+/).filter(Boolean).map((term) => {
    if (!/^[a-z0-9_.+%_-]+$/i.test(term)) return term;
    const literal = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(?<![a-z])${literal}`, "gi");
  });
  if (!terms.length) return <>{text}</>;
  return <Highlighter autoEscape searchWords={terms} textToHighlight={text} highlightClassName="search-match" />;
}
