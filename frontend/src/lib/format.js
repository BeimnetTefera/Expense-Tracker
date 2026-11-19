import { marked } from "marked";
import DOMPurify from "dompurify";

export const etb = (cents) =>
  (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtMs = (ms) => (ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : ms + " ms");

export const shortDate = (iso) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// LLM replies are markdown. Sanitize: the model can echo text the user typed.
export const markdownToHtml = (text) => DOMPurify.sanitize(marked.parse(text || ""));

// Compact, colour-coded JSON for tool arguments. Escape first, then colour.
export function highlightJson(raw) {
  let text;
  try {
    text = JSON.stringify(JSON.parse(raw));
  } catch {
    return esc(raw);
  }
  text = text.replace(/,"/g, ', "').replace(/":/g, '": ');
  return esc(text).replace(
    /(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(-?\d+(?:\.\d+)?)\b|\b(true|false|null)\b/g,
    (m, str, colon, num, lit) => {
      if (str) return colon ? `<span class="j-key">${str}</span>${colon}` : `<span class="j-str">${str}</span>`;
      if (num) return `<span class="j-num">${num}</span>`;
      return `<span class="j-lit">${lit}</span>`;
    },
  );
}
