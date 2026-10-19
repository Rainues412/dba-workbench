import type { VaultSecret } from "./crypto";

// Edge/Chromium CSV columns follow the same mapping used by Bitwarden's
// Chrome importer. Parse quoted commas/newlines without altering passwords.
export function parseEdgeCsv(text: string): { items: VaultSecret[]; emptyPasswords: number } {
  const rows: string[][] = [];
  let row: string[] = [], value = "", quoted = false, closed = false;
  const input = text.replace(/^\uFEFF/, "");
  function field() { row.push(value); value = ""; closed = false; }
  function endRow() { field(); if (row.some((cell) => cell !== "")) rows.push(row); row = []; }
  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    if (quoted) {
      if (char === '"') {
        if (input[index + 1] === '"') { value += '"'; index += 1; }
        else { quoted = false; closed = true; }
      } else value += char;
    } else if (char === ",") field();
    else if (char === "\r" || char === "\n") { endRow(); if (char === "\r" && input[index + 1] === "\n") index += 1; }
    else if (char === '"' && !value && !closed) quoted = true;
    else if (closed || char === '"') throw new Error("CSV 引号格式无效，尚未导入任何条目");
    else value += char;
  }
  if (quoted) throw new Error("CSV 引号未闭合，尚未导入任何条目");
  if (value || row.length || closed) endRow();
  const headers = rows.shift()?.map((cell) => cell.trim().toLowerCase()) ?? [];
  if (!headers.length || new Set(headers).size !== headers.length || !["url", "username", "password"].every((name) => headers.includes(name))) {
    throw new Error("不是受支持的 Edge 密码 CSV：需要 url、username、password 列");
  }
  if (rows.length > 5000) throw new Error("单次最多导入 5000 条，请分批导出");
  const items: VaultSecret[] = [];
  let emptyPasswords = 0;
  for (const cells of rows) {
    if (cells.length !== headers.length) throw new Error("CSV 列数不一致，尚未导入任何条目");
    const get = (name: string) => cells[headers.indexOf(name)] ?? "";
    if (!get("password")) { emptyPasswords += 1; continue; }
    const url = get("url").trim();
    let site = get("name").trim();
    if (!site) { try { site = new URL(url).hostname; } catch { /* Keep unsupported URLs as data, never open them. */ } }
    items.push({ site: site || "Edge 导入条目", url, username: get("username"), password: get("password"), notes: get("note") || get("notes"), category: "Edge 导入", favorite: false });
  }
  if (!items.length) throw new Error("CSV 中没有包含密码的有效条目");
  return { items, emptyPasswords };
}

export function loginIdentity(secret: VaultSecret): string {
  return JSON.stringify([secret.url.trim(), secret.username, secret.password]);
}

// A vault-key-derived HMAC avoids exposing guessable password fingerprints to
// the server and gives retries stable item keys without storing plaintext.
export async function edgeImportKey(dek: Uint8Array<ArrayBuffer>, secret: VaultSecret): Promise<string> {
  const source = await crypto.subtle.importKey("raw", dek, "HKDF", false, ["deriveKey"]);
  const hmac = await crypto.subtle.deriveKey({ name: "HKDF", hash: "SHA-256", salt: new Uint8Array(32), info: new TextEncoder().encode("dba-vault:edge-csv:v1") }, source, { name: "HMAC", hash: "SHA-256", length: 256 }, false, ["sign"]);
  const digest = new Uint8Array(await crypto.subtle.sign("HMAC", hmac, new TextEncoder().encode(loginIdentity(secret))));
  return `edge_csv_${Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}
