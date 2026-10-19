import { describe, expect, it } from "vitest";
import { parseEdgeCsv, loginIdentity } from "../vault/edgeCsv";

describe("Edge CSV import", () => {
  it("preserves quoted password punctuation, whitespace and embedded newlines", () => {
    const result = parseEdgeCsv('\uFEFFname,url,username,password,note\r\nExample,https://example.test,user,"  a,""b\r\nc  ","one,two"\r\n');
    expect(result.items[0]).toMatchObject({ site: "Example", password: '  a,"b\r\nc  ', notes: "one,two", category: "Edge 导入" });
  });
  it("maps reordered columns and skips empty passwords without trimming secrets", () => {
    const result = parseEdgeCsv('password,username,url\n secret , user ,https://example.test\n,skip,https://empty.test\n');
    expect(result.emptyPasswords).toBe(1);
    expect(result.items[0]).toMatchObject({ site: "example.test", username: " user ", password: " secret " });
    expect(loginIdentity(result.items[0])).toBe(JSON.stringify(["https://example.test", " user ", " secret "]));
  });
  it.each([
    'url,username,password\na,b,"secret',
    'url,username,password\na,b,"secret"suffix',
    'url,username,password\na,b,se"cret',
    'url,username,password\na,b,secret,extra',
    'url,username,password,password\na,b,secret,secret',
    'url,username\na,b',
    'url,username,password\na,b,',
  ])("rejects malformed input without echoing secrets", (input) => {
    expect(() => parseEdgeCsv(input)).toThrow();
    try { parseEdgeCsv(input); } catch (error) { expect(String(error)).not.toContain("secret"); }
  });
  it("limits batch size before import", () => {
    expect(() => parseEdgeCsv('url,username,password\n' + 'a,b,c\n'.repeat(5001))).toThrow("5000");
  });
});
