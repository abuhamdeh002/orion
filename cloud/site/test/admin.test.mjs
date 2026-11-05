import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import worker, { applyEvent, handle } from "../src/worker.mjs";

// Vitest 2 does not resolve node:sqlite as an import, so load it the CommonJS way.
const { DatabaseSync } = createRequire(import.meta.url)("node:sqlite");

// A small D1 look-alike over node:sqlite, so the real SQL in worker.mjs runs.
function d1() {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../schema.sql", import.meta.url), "utf8"));
  return {
    prepare(sql) {
      const statement = db.prepare(sql);
      let args = [];
      const bound = {
        bind(...values) {
          args = values;
          return bound;
        },
        async run() {
          return statement.run(...args);
        },
        async first() {
          return statement.get(...args) ?? null;
        },
        async all() {
          return { results: statement.all(...args) };
        },
      };
      return bound;
    },
  };
}

function env(extra = {}) {
  return { DB: d1(), LICENSE_PRIVATE_HEX: randomBytes(32).toString("hex"), ADMIN_TOKEN: "a".repeat(40), ...extra };
}

const checkout = {
  type: "checkout.session.completed",
  data: { object: { id: "cs_test_abcdefghijkl", customer: "cus_1", customer_email: "a@b.c", mode: "subscription", metadata: {} } },
};

describe("site worker", () => {
  it("exports a fetch handler for Workers", () => {
    expect(typeof worker.fetch).toBe("function");
  });

  it("only the checkout session id unlocks a license", async () => {
    const e = env();
    await applyEvent(e.DB, e, checkout);
    const byEmail = await handle(new Request("https://orion.test/api/portal?email=a@b.c"), e);
    expect(byEmail.status).toBe(400);
    const guessed = await handle(new Request("https://orion.test/api/portal?session_id=cs_test_zzzzzzzzzzzz"), e);
    expect(guessed.status).toBe(404);
    const mine = await handle(new Request("https://orion.test/api/portal?session_id=cs_test_abcdefghijkl"), e);
    const body = await mine.json();
    expect(body.found).toBe(true);
    expect(body.license.split(".")).toHaveLength(2);
  });

  it("subscription licenses expire with the billing period, not in 2100", async () => {
    const e = env();
    const now = Date.UTC(2026, 10, 4);
    await applyEvent(e.DB, e, checkout, now);
    const row = await e.DB.prepare("SELECT license FROM customers WHERE id = ?").bind("cus_1").first();
    const payload = JSON.parse(Buffer.from(row.license.split(".")[0], "base64url").toString("utf8"));
    expect(payload.exp).toBeLessThan(now / 1000 + 40 * 86400);
  });

  it("admin routes need the admin token", async () => {
    const e = env();
    expect((await handle(new Request("https://orion.test/api/admin/summary"), e)).status).toBe(401);
    const wrong = new Request("https://orion.test/api/admin/summary", { headers: { Authorization: "Bearer nope" } });
    expect((await handle(wrong, e)).status).toBe(401);
    const right = new Request("https://orion.test/api/admin/summary", { headers: { Authorization: `Bearer ${"a".repeat(40)}` } });
    expect((await handle(right, e)).status).toBe(200);
  });

  it("a weak or missing admin token locks admin entirely", async () => {
    const e = env({ ADMIN_TOKEN: "short" });
    const request = new Request("https://orion.test/api/admin/summary", { headers: { Authorization: "Bearer short" } });
    expect((await handle(request, e)).status).toBe(401);
  });

  it("the webhook refuses unsigned events", async () => {
    const e = env({ STRIPE_WEBHOOK_SECRET: "whsec_x" });
    const request = new Request("https://orion.test/api/stripe/webhook", { method: "POST", body: JSON.stringify(checkout) });
    expect((await handle(request, e)).status).toBe(400);
  });
});
