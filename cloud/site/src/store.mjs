import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mintLicense } from "./billing.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "data");
const file = join(root, "store.json");
// The license signing key is a secret: a Worker secret in production, cloud/site/.dev.vars locally.
// There is deliberately no fallback, so a missing key fails loudly instead of signing with a known one.
function licenseKey(env) {
  const value = env?.LICENSE_PRIVATE_HEX || (typeof process !== "undefined" ? process.env.LICENSE_PRIVATE_HEX : undefined);
  if (!value || !/^[0-9a-f]{64}$/i.test(value)) throw new Error("LICENSE_PRIVATE_HEX is not set.");
  return value;
}

function localKey() {
  const vars = join(dirname(fileURLToPath(import.meta.url)), "..", ".dev.vars");
  if (!process.env.LICENSE_PRIVATE_HEX && existsSync(vars)) {
    const line = readFileSync(vars, "utf8").split(/\r?\n/).find((item) => item.startsWith("LICENSE_PRIVATE_HEX="));
    if (line) process.env.LICENSE_PRIVATE_HEX = line.slice("LICENSE_PRIVATE_HEX=".length).trim();
  }
  return licenseKey();
}

function blank() {
  return { pin: null, customers: [], devices: [], flags: { trials: true, relay: true, phoneSms: false }, notes: [], audit: [] };
}

export function loadStore() {
  if (!existsSync(file)) return blank();
  try {
    const store = { ...blank(), ...JSON.parse(readFileSync(file, "utf8")) };
    if (store.pin && !String(store.pin).startsWith("scrypt:")) {
      store.pin = hashPin(store.pin);
      save(store);
    }
    return store;
  } catch {
    return blank();
  }
}

function save(store) {
  mkdirSync(root, { recursive: true });
  writeFileSync(file, JSON.stringify(store, null, 2));
}

function audit(store, action, detail) {
  store.audit.unshift({ action, detail, at: new Date().toISOString() });
  store.audit = store.audit.slice(0, 80);
}

export function publicState(store) {
  const cloud = store.customers.filter((item) => item.cloud && item.status === "active");
  const lifetime = store.customers.filter((item) => item.plan === "lifetime" && item.status === "active");
  return {
    needsSetup: !store.pin,
    customers: store.customers,
    devices: store.devices,
    flags: store.flags,
    notes: store.notes,
    audit: store.audit,
    metrics: {
      customers: store.customers.length,
      active: store.customers.filter((item) => item.status === "active").length,
      lifetime: lifetime.length,
      cloud: cloud.length,
      revenue: store.customers.reduce((sum, item) => sum + Number(item.amount || 0), 0),
      mrr: cloud.reduce((sum, item) => sum + Number(item.monthly || 0), 0),
    },
  };
}

// The admin PIN is stored as a salted scrypt hash, never as the PIN itself.
export function hashPin(pin, salt = randomBytes(16).toString("hex")) {
  return `scrypt:${salt}:${scryptSync(String(pin), salt, 32).toString("hex")}`;
}

function pinMatches(stored, pin) {
  if (!stored || !String(stored).startsWith("scrypt:")) return false;
  const [, salt, digest] = String(stored).split(":");
  const expected = Buffer.from(digest, "hex");
  const actual = scryptSync(String(pin || ""), salt, 32);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export function setupPin(store, pin) {
  if (store.pin) return { ok: false, error: "A PIN is already set." };
  if (!pin || String(pin).length < 6) return { ok: false, error: "Use at least 6 characters." };
  store.pin = hashPin(pin);
  audit(store, "admin_pin_set", "Admin PIN created");
  save(store);
  return { ok: true };
}

export function checkPin(store, pin) {
  return pinMatches(store.pin, pin);
}

export function addCustomer(store, body) {
  const email = String(body.email || "").trim().toLowerCase();
  if (!email.includes("@")) return { ok: false, error: "Need an email." };
  const plan = ["lifetime", "cloud", "bundle"].includes(body.plan) ? body.plan : "lifetime";
  const cloud = plan !== "lifetime";
  const customer = {
    id: `cus_${randomBytes(4).toString("hex")}`,
    email,
    plan,
    cloud,
    status: "active",
    amount: Number(body.amount || 0),
    monthly: cloud ? Number(body.monthly || 12) : 0,
    license: null,
    created: new Date().toISOString(),
  };
  customer.license = mintLicense(localKey(), { plan, cloud, exp: plan === "cloud" ? Math.floor(Date.now() / 1000) + 32 * 24 * 3600 : 4102444800, sub: customer.id });
  store.customers.unshift(customer);
  audit(store, "customer_added", email);
  save(store);
  return { ok: true, customer };
}

export function patchCustomer(store, id, action, body = {}) {
  const customer = store.customers.find((item) => item.id === id);
  if (!customer) return { ok: false, error: "No such customer." };
  if (action === "revoke") {
    customer.status = "revoked";
    customer.license = null;
    audit(store, "license_revoked", customer.email);
  } else if (action === "extend") {
    const days = Number(body.days || 30);
    customer.status = "active";
    customer.cloud = true;
    customer.license = mintLicense(localKey(), { plan: customer.plan, cloud: true, exp: Math.floor(Date.now() / 1000) + days * 86400, sub: customer.id });
    audit(store, "license_extended", `${customer.email} +${days}d`);
  } else if (action === "note") {
    const text = String(body.text || "").trim();
    if (!text) return { ok: false, error: "Empty note." };
    store.notes.unshift({ id: randomBytes(3).toString("hex"), customer: customer.email, text, at: new Date().toISOString() });
    audit(store, "note", customer.email);
  }
  save(store);
  return { ok: true, customer };
}

export function addDevice(store, body) {
  const customer = store.customers.find((item) => item.id === body.customer);
  if (!customer) return { ok: false, error: "Pick a customer." };
  const device = { id: `dev_${randomBytes(3).toString("hex")}`, customer: customer.id, email: customer.email, kind: body.kind || "phone", name: body.name || "S24 Ultra", revoked: false, at: new Date().toISOString() };
  store.devices.unshift(device);
  audit(store, "device_added", `${device.name} ${customer.email}`);
  save(store);
  return { ok: true, device };
}

export function revokeDevice(store, id) {
  const device = store.devices.find((item) => item.id === id);
  if (!device) return { ok: false, error: "No such device." };
  device.revoked = true;
  audit(store, "device_revoked", device.name);
  save(store);
  return { ok: true };
}

export function setFlag(store, name, enabled) {
  if (!(name in store.flags)) return { ok: false, error: "Unknown flag." };
  store.flags[name] = Boolean(enabled);
  audit(store, "flag", `${name}=${store.flags[name]}`);
  save(store);
  return { ok: true, flags: store.flags };
}
