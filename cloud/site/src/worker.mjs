// Production site worker: Stripe checkout, the webhook that mints licenses, the customer portal, and admin.
// Storage is D1 (schema.sql). Secrets: LICENSE_PRIVATE_HEX, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, ADMIN_TOKEN.
import { timingSafeEqual } from "node:crypto";
import { checkoutBody, mintLicense, verifyStripeSignature } from "./billing.mjs";

const LIFETIME_EXP = 4_102_444_800;
const CLOUD_DAYS = 35;

// The license signing key is a secret: a Worker secret in production, cloud/site/.dev.vars locally.
// There is deliberately no fallback, so a missing key fails loudly instead of signing with a known one.
function licenseKey(env) {
  const value = env?.LICENSE_PRIVATE_HEX || (typeof process !== "undefined" ? process.env.LICENSE_PRIVATE_HEX : undefined);
  if (!value || !/^[0-9a-f]{64}$/i.test(value)) throw new Error("LICENSE_PRIVATE_HEX is not set.");
  return value;
}

function sameSecret(given, expected) {
  if (!given || !expected || expected.length < 32) return false;
  const left = Buffer.from(given);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function isAdmin(request, env) {
  const token = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  return sameSecret(token, env.ADMIN_TOKEN);
}

function cloudExpiry(now = Date.now()) {
  return Math.floor(now / 1000) + CLOUD_DAYS * 86400;
}

async function audit(DB, action, customer) {
  await DB.prepare("INSERT INTO audit (action, customer, at) VALUES (?, ?, ?)").bind(action, customer || null, new Date().toISOString()).run();
}

// Applies one verified Stripe event to D1. Returns what happened, for the response and the tests.
export async function applyEvent(DB, env, event, now = Date.now()) {
  const object = event.data?.object || {};
  if (event.type === "checkout.session.completed") {
    const plan = object.mode === "subscription" ? "cloud" : "lifetime";
    const cloud = plan === "cloud" || object.metadata?.bundle === "1";
    const exp = plan === "lifetime" ? LIFETIME_EXP : cloudExpiry(now);
    const license = mintLicense(licenseKey(env), { plan, cloud, exp, sub: object.customer });
    await DB.prepare(
      "INSERT INTO customers (id, email, plan, cloud, license, session_id) VALUES (?, ?, ?, ?, ?, ?) " +
        "ON CONFLICT(id) DO UPDATE SET email = excluded.email, plan = excluded.plan, cloud = excluded.cloud, " +
        "license = excluded.license, session_id = excluded.session_id",
    )
      .bind(object.customer, object.customer_email || null, plan, cloud ? 1 : 0, license, object.id)
      .run();
    await audit(DB, "checkout", object.customer);
    return { ok: true, plan };
  }
  if (event.type === "invoice.paid" && object.subscription) {
    // Each paid month re-issues a cloud license that runs to just past the next renewal.
    const row = await DB.prepare("SELECT plan, cloud FROM customers WHERE id = ?").bind(object.customer).first();
    if (!row) return { ok: true, plan: "unknown" };
    const license = mintLicense(licenseKey(env), { plan: row.plan, cloud: true, exp: cloudExpiry(now), sub: object.customer });
    await DB.prepare("UPDATE customers SET license = ?, cloud = 1 WHERE id = ?").bind(license, object.customer).run();
    await audit(DB, "renewed", object.customer);
    return { ok: true, plan: "renewed" };
  }
  if (event.type === "customer.subscription.deleted") {
    await DB.prepare("UPDATE customers SET cloud = 0 WHERE id = ?").bind(object.customer).run();
    await audit(DB, "subscription_ended", object.customer);
    return { ok: true, plan: "ended" };
  }
  return { ok: true, plan: "ignored" };
}

export async function handle(request, env) {
  const url = new URL(request.url);
  const DB = env.DB;

  if (request.method === "POST" && url.pathname === "/api/checkout") {
    const body = await request.json();
    const prices = { lifetime: env.PRICE_LIFETIME, cloud: env.PRICE_CLOUD, bundle: env.PRICE_BUNDLE };
    if (!prices[body.plan]) return Response.json({ error: "Unknown plan." }, { status: 400 });
    const mode = body.plan === "lifetime" ? "payment" : "subscription";
    const params = checkoutBody({
      price: prices[body.plan],
      mode,
      // Stripe fills in the session id; the portal uses it to prove this browser made the purchase.
      success: `${url.origin}/app?session_id={CHECKOUT_SESSION_ID}`,
      cancel: `${url.origin}/`,
      email: body.email,
    });
    const response = await fetch("https://api.stripe.com/v1/checkout/sessions", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, "Content-Type": "application/x-www-form-urlencoded" },
      body: params,
    });
    const session = await response.json();
    return Response.json({ url: session.url });
  }

  if (request.method === "POST" && url.pathname === "/api/stripe/webhook") {
    const payload = await request.text();
    const header = request.headers.get("stripe-signature") || "";
    if (!env.STRIPE_WEBHOOK_SECRET || !verifyStripeSignature(payload, header, env.STRIPE_WEBHOOK_SECRET)) {
      return new Response("Bad signature.", { status: 400 });
    }
    return Response.json(await applyEvent(DB, env, JSON.parse(payload)));
  }

  if (url.pathname === "/api/portal") {
    // Only the checkout session id (an unguessable value Stripe hands the buyer) unlocks a license.
    const session = url.searchParams.get("session_id") || "";
    if (!/^cs_[A-Za-z0-9_]{10,}$/.test(session)) {
      return Response.json({ found: false, error: "Open the link from your checkout receipt." }, { status: 400 });
    }
    const row = await DB.prepare("SELECT email, plan, cloud, license FROM customers WHERE session_id = ?").bind(session).first();
    if (!row) return Response.json({ found: false, error: "Still processing. Refresh in a few seconds." }, { status: 404 });
    return Response.json({ found: true, email: row.email, plan: row.plan, cloud: Boolean(row.cloud), license: row.license });
  }

  if (url.pathname.startsWith("/api/admin/")) {
    if (!isAdmin(request, env)) return Response.json({ error: "Admin token required." }, { status: 401 });
    if (url.pathname === "/api/admin/summary") {
      const totals = await DB.prepare("SELECT COUNT(*) AS customers, SUM(cloud) AS cloud FROM customers").first();
      const recent = await DB.prepare("SELECT action, customer, at FROM audit ORDER BY id DESC LIMIT 50").all();
      return Response.json({ customers: totals?.customers || 0, cloud: totals?.cloud || 0, audit: recent?.results || [] });
    }
    return Response.json({ error: "Not found." }, { status: 404 });
  }

  if (env.ASSETS) return env.ASSETS.fetch(request);
  return new Response("ORION", { status: 200 });
}

export default {
  fetch: (request, env) => handle(request, env),
};
