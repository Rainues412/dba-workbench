import { describe, expect, it } from "vitest";
import { databaseMeta } from "../components/DatabaseLabel";

describe("database label palette", () => {
  it("keeps the official MongoDB green distinct from MySQL and Other", () => {
    expect(databaseMeta.MongoDB.color).toBe("#00684a");
    expect(databaseMeta.MongoDB.color).not.toBe(databaseMeta.MySQL.color);
    expect(databaseMeta.MongoDB.tint).not.toBe(databaseMeta.MySQL.tint);
    expect(databaseMeta.MongoDB.color).not.toBe(databaseMeta["其他"].color);
  });
});
