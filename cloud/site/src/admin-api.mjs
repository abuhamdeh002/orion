import {
  addCustomer,
  addDevice,
  checkPin,
  loadStore,
  patchCustomer,
  publicState,
  revokeDevice,
  setFlag,
  setupPin,
} from "./store.mjs";

const sessions = new Set();

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...extra } });
}

async function read(request) {
  if (request.method === "GET") return {};
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export async function adminRequest(request) {
  const url = new URL(request.url);
  const store = loadStore();
  const token = (request.headers.get("authorization") || "").replace("Bearer ", "");
  const authed = sessions.has(token);

  if (url.pathname === "/api/portal" && request.method === "GET") {
    const email = (url.searchParams.get("email") || "").trim().toLowerCase();
    const customer = store.customers.find((item) => item.email === email && item.status === "active");
    if (!customer) return json({ found: false });
    return json({
      found: true,
      email: customer.email,
      plan: customer.plan,
      cloud: customer.cloud,
      license: customer.license,
      devices: store.devices.filter((item) => item.customer === customer.id),
    });
  }

  if (url.pathname === "/api/admin/session" && request.method === "POST") {
    const body = await read(request);
    if (!store.pin) {
      const created = setupPin(store, body.pin);
      if (!created.ok) return json(created, 400);
    } else if (!checkPin(store, body.pin)) {
      return json({ ok: false, error: "Wrong PIN." }, 401);
    }
    const session = crypto.randomUUID();
    sessions.add(session);
    return json({ ok: true, token: session, ...publicState(loadStore()) });
  }

  if (!url.pathname.startsWith("/api/admin")) return null;
  if (url.pathname === "/api/admin/state" && request.method === "GET") {
    if (!store.pin) return json({ needsSetup: true });
    if (!authed) return json({ locked: true }, 401);
    const health = await pcHealth();
    return json({ ...publicState(store), health });
  }
  if (!authed) return json({ locked: true }, 401);

  const body = await read(request);
  if (url.pathname === "/api/admin/customers" && request.method === "POST") return json(addCustomer(loadStore(), body));
  const customer = url.pathname.match(/^\/api\/admin\/customers\/([^/]+)\/(revoke|extend|note)$/);
  if (customer && request.method === "POST") return json(patchCustomer(loadStore(), customer[1], customer[2], body));
  if (url.pathname === "/api/admin/devices" && request.method === "POST") return json(addDevice(loadStore(), body));
  const device = url.pathname.match(/^\/api\/admin\/devices\/([^/]+)\/revoke$/);
  if (device && request.method === "POST") return json(revokeDevice(loadStore(), device[1]));
  if (url.pathname === "/api/admin/flags" && request.method === "POST") return json(setFlag(loadStore(), body.name, body.enabled));
  return json({ error: "Unknown admin route." }, 404);
}

async function pcHealth() {
  try {
    const response = await fetch("http://127.0.0.1:8765/health");
    const body = await response.json();
    return { online: response.ok, provider: body.provider || "", license: body.license || "" };
  } catch {
    return { online: false, provider: "", license: "" };
  }
}

export function adminPlugin() {
  return {
    name: "orion-admin",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        const request = new Request(`http://127.0.0.1${req.url}`, { method: req.method, headers: req.headers });
        if (req.method !== "GET" && req.method !== "HEAD") {
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          const response = await adminRequest(new Request(`http://127.0.0.1${req.url}`, { method: req.method, headers: req.headers, body: Buffer.concat(chunks) }));
          if (!response) return next();
          res.statusCode = response.status;
          res.setHeader("Content-Type", "application/json");
          res.end(Buffer.from(await response.arrayBuffer()));
          return;
        }
        const response = await adminRequest(request);
        if (!response) return next();
        res.statusCode = response.status;
        res.setHeader("Content-Type", "application/json");
        res.end(Buffer.from(await response.arrayBuffer()));
      });
    },
  };
}
