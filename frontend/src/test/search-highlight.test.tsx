import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SearchHighlight } from "../components/SearchHighlight";

afterEach(cleanup);

describe("title match highlighting", () => {
  it.each([
    ["MySQL 故障排查，故障恢复", " mysql   故障 ", ["MySQL", "故障", "故障"]],
    ["Oracle RAC 与 Oracle", "rac", ["RAC"]],
    ["C++ a.b [备份]", "C++ a.b [备份]", ["C++", "a.b", "[备份]"]],
    ["备份恢复", "   ", []],
  ])("highlights literal matching terms in %s", (text, query, expected) => {
    const { container } = render(<SearchHighlight text={text} query={query} />);
    expect(container.textContent).toBe(text);
    expect([...container.querySelectorAll("mark")].map((node) => node.textContent)).toEqual(expected);
  });

  it("renders HTML-like titles as plain text", () => {
    const text = '<img src=x onerror="alert(1)">';
    const { container } = render(<SearchHighlight text={text} query="<img" />);
    expect(container.textContent).toBe(text);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("mark")).toHaveTextContent("<img");
  });
});
