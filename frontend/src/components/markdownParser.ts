import { Marked } from "marked";
import { gfmHeadingId } from "marked-gfm-heading-id";

export function createMarkdownParser() {
  return new Marked(gfmHeadingId({ prefix: "preview-" }), {
    renderer: {
      paragraph({ text }) {
        // Typora's standalone placeholder is represented by the preview's outline.
        return /^\[toc\]$/i.test(text.trim()) ? "" : false;
      },
    },
  });
}
