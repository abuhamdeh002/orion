import { createHmac, sign, timingSafeEqual } from "node:crypto";

const PKCS8_PREFIX = Buffer.from("302e020100300506032b657004220420", "hex");

export function mintLicense(privateRawHex, payload) {
  const body = Buffer.from(JSON.stringify(sort(payload)));
  const key = Buffer.concat([PKCS8_PREFIX, Buffer.from(privateRawHex, "hex")]);
  const signature = sign(null, body, { key, format: "der", type: "pkcs8" });
  return `${b64(body)}.${b64(signature)}`;
}

export function checkoutBody({ price, mode, success, cancel, email }) {
  const params = new URLSearchParams();
  params.set("mode", mode);
  params.set("line_items[0][price]", price);
  params.set("line_items[0][quantity]", "1");
  params.set("success_url", success);
  params.set("cancel_url", cancel);
  if (email) params.set("customer_email", email);
  params.set("automatic_tax[enabled]", "false");
  return params;
}

export function verifyStripeSignature(payload, header, secret, now = Date.now()) {
  const parts = Object.fromEntries(header.split(",").map((piece) => piece.split("=", 2)));
  const timestamp = Number(parts.t);
  if (!timestamp || Math.abs(now / 1000 - timestamp) > 300) return false;
  const expected = createHmac("sha256", secret).update(`${parts.t}.${payload}`).digest("hex");
  const given = Buffer.from(parts.v1 || "", "hex");
  const actual = Buffer.from(expected, "hex");
  return given.length === actual.length && timingSafeEqual(given, actual);
}

export function applyWebhook(db, event) {
  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    const plan = session.mode === "subscription" ? "cloud" : "lifetime";
    db.customers.set(session.customer, { email: session.customer_email, plan, cloud: plan === "cloud" || session.metadata?.bundle === "1" });
    db.audit.push({ action: "checkout", customer: session.customer });
    return { ok: true, plan };
  }
  if (event.type === "customer.subscription.deleted") {
    const customer = db.customers.get(event.data.object.customer);
    if (customer) customer.cloud = false;
    db.audit.push({ action: "subscription_ended", customer: event.data.object.customer });
    return { ok: true, plan: "ended" };
  }
  return { ok: true, plan: "ignored" };
}

export const SCHEMA = `
CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, email TEXT, plan TEXT, cloud INTEGER, license TEXT);
CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, customer TEXT, kind TEXT, revoked INTEGER);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, customer TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS flags (name TEXT PRIMARY KEY, enabled INTEGER);
`;

export function licenseEmail(to, license) {
  return { to, subject: "Your ORION license", text: `Your key:\n${license}\nInstall the PC app and the Android APK from the portal.` };
}

function sort(value) {
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]]));
}

function b64(value) {
  return Buffer.from(value).toString("base64url");
}
