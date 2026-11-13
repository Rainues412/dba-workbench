import { SearchHighlight } from "./SearchHighlight";

export function FileName({ text, path = "", query = "" }: { text: string; path?: string; query?: string }) {
  const basename = path.split(/[\\/]/).pop();
  // A record title can be prose containing a dot; only split an actual filename.
  const suffix = (basename === text || (path && text === path)) ? text.match(/(?:\.tar\.(?:gz|bz2|xz|zst)|\.[a-zA-Z0-9]{1,12})$/)?.[0] : undefined;
  if (!suffix || text.length === suffix.length) return <SearchHighlight text={text} query={query} />;
  return <span className="filename"><span className="filename-stem"><SearchHighlight text={text.slice(0, -suffix.length)} query={query} /></span><span className="filename-extension"><SearchHighlight text={suffix} query={query} /></span></span>;
}
