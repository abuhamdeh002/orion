import { createHmac, randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import { applyWebhook, checkoutBody, mintLicense, verifyStripeSignature } from "../src/billing.mjs";

describe("billing", () => {
  it("builds a checkout session for a lifetime purchase", () => {
    const body = checkoutBody({ price: "price_lifetime", mode: "payment", success: "https://orion.test/app", cancel: "https://orion.test/", email: "a@b.c" });
    expect(body.get("mode")).toBe("payment");
    expect(body.get("line_items[0][price]")).toBe("price_lifetime");
  });

  it("accepts a Stripe signature and ignores a stale one", () => {
    const payload = '{"id":"evt_1"}';
    const secret = "whsec_test";
    const stamp = 1_700_000_000;
    const digest = createHmac("sha256", secret).update(`${stamp}.${payload}`).digest("hex");
    expect(verifyStripeSignature(payload, `t=${stamp},v1=${digest}`, secret, stamp * 1000)).toBe(true);
    expect(verifyStripeSignature(payload, `t=${stamp},v1=${digest}`, secret, (stamp + 1000) * 1000)).toBe(false);
  });

  it("mints a license and records a completed checkout", () => {
    const key = mintLicense(randomBytes(32).toString("hex"), {
      plan: "lifetime",
      cloud: false,
      exp: 4_000_000_000,
    });
    expect(key.split(".")).toHaveLength(2);
    const db = { customers: new Map(), audit: [] };
    const result = applyWebhook(db, {
      type: "checkout.session.completed",
      data: { object: { customer: "cus_1", customer_email: "a@b.c", mode: "payment", metadata: {} } },
    });
    expect(result.plan).toBe("lifetime");
    expect(db.customers.get("cus_1").email).toBe("a@b.c");
    const ended = applyWebhook(db, { type: "customer.subscription.deleted", data: { object: { customer: "cus_1" } } });
    expect(ended.plan).toBe("ended");
    expect(db.audit).toHaveLength(2);
  });
});

describe("admin pin", () => {
  it("stores a salted hash and checks it in constant time", async () => {
    const { hashPin, checkPin } = await import("../src/store.mjs");
    const stored = hashPin("246813");
    expect(stored.startsWith("scrypt:")).toBe(true);
    expect(stored.includes("246813")).toBe(false);
    expect(checkPin({ pin: stored }, "246813")).toBe(true);
    expect(checkPin({ pin: stored }, "000000")).toBe(false);
    expect(checkPin({ pin: "246813" }, "246813")).toBe(false);
  });
});
