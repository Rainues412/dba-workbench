import { Lexer, Marked, Tokenizer } from "marked";
import { gfmHeadingId } from "marked-gfm-heading-id";

export function createMarkdownParser() {
  // Reuse Marked's legacy image tokenizer for Typora destinations containing spaces.
  // Keep the main parser in GFM mode so tables, fences and normal links are unchanged.
  const legacy = new Tokenizer();
  new Lexer({ pedantic: true, tokenizer: legacy });
  return new Marked(gfmHeadingId({ prefix: "preview-" }), {
    tokenizer: {
      link(source) {
        if (!source.startsWith("![")) return false;
        const image = legacy.link(source);
        return image?.type === "image" && /[ \t]/.test(image.href) && !/[\r\n]/.test(image.raw) ? image : false;
      },
    },
    renderer: {
      paragraph({ text }) {
        // Typora's standalone placeholder is represented by the preview's outline.
        return /^\[toc\]$/i.test(text.trim()) ? "" : false;
      },
    },
  });
}
