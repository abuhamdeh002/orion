import { describe, expect, it } from "vitest";
import { parseRole, relayToken, verifyRelayToken } from "../src/auth";

const secret = "a-test-secret-that-is-at-least-32-characters";

describe("relay auth", () => {
  it("accepts the right token for the right account and role", async () => {
    const token = await relayToken(secret, "acct_1", "pc");
    expect(await verifyRelayToken(secret, "acct_1", "pc", token)).toBe(true);
  });

  it("rejects any bearer string, another account, or another role", async () => {
    const phone = await relayToken(secret, "acct_1", "phone");
    expect(await verifyRelayToken(secret, "acct_1", "phone", "anything")).toBe(false);
    expect(await verifyRelayToken(secret, "acct_2", "phone", phone)).toBe(false);
    expect(await verifyRelayToken(secret, "acct_1", "pc", phone)).toBe(false);
  });

  it("refuses everything when the secret is missing or weak", async () => {
    const token = await relayToken("short", "acct_1", "pc");
    expect(await verifyRelayToken(undefined, "acct_1", "pc", token)).toBe(false);
    expect(await verifyRelayToken("short", "acct_1", "pc", token)).toBe(false);
  });

  it("only knows two roles", () => {
    expect(parseRole("pc")).toBe("pc");
    expect(parseRole("admin")).toBeNull();
  });
});
