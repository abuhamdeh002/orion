import { DurableObject } from "cloudflare:workers";
import { parseRole, verifyRelayToken } from "./auth";
import { acceptFrame, catchUp, fcmBody, type Frame, type RoomState } from "./frames";

export interface Env {
  ROOM: DurableObjectNamespace<AccountRoom>;
  RELAY_SECRET?: string;
  FCM_SERVER_KEY?: string;
  FCM_PROJECT?: string;
}

type Saved = { queue: Frame[]; fcmTokens: string[] };

export class AccountRoom extends DurableObject<Env> {
  private pc: WebSocket | null = null;
  private phones = new Map<string, WebSocket>();
  private state: RoomState = { pcOnline: false, phones: 0, queue: [] };
  private fcmTokens: string[] = [];

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Catch-up events and push tokens survive the object being evicted or redeployed.
    ctx.blockConcurrencyWhile(async () => {
      const saved = await ctx.storage.get<Saved>("room");
      if (saved) {
        this.state = { ...this.state, queue: saved.queue || [] };
        this.fcmTokens = saved.fcmTokens || [];
      }
    });
  }

  private async persist(): Promise<void> {
    await this.ctx.storage.put<Saved>("room", { queue: this.state.queue, fcmTokens: this.fcmTokens });
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      if (new URL(request.url).pathname.endsWith("/catchup")) {
        return Response.json({ events: catchUp(this.state) });
      }
      return new Response("Expected a WebSocket.", { status: 426 });
    }
    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    // The entry worker already checked the token for this exact role.
    const role = new URL(request.url).searchParams.get("role") === "pc" ? "pc" : "phone";
    const device = new URL(request.url).searchParams.get("device") || crypto.randomUUID();
    server.accept();
    if (role === "pc") {
      this.pc?.close(4000, "replaced");
      this.pc = server;
      this.state = { ...this.state, pcOnline: true };
    } else {
      this.phones.set(device, server);
      this.state = { ...this.state, phones: this.phones.size };
      const token = new URL(request.url).searchParams.get("fcm");
      if (token && !this.fcmTokens.includes(token)) {
        this.fcmTokens = [...this.fcmTokens, token].slice(-10);
        await this.persist();
      }
    }
    server.addEventListener("message", (event) => {
      void this.onMessage(role, device, String(event.data));
    });
    server.addEventListener("close", () => {
      if (role === "pc" && this.pc === server) {
        this.pc = null;
        this.state = { ...this.state, pcOnline: false };
        this.broadcast({ type: "presence", text: "offline" });
      } else {
        this.phones.delete(device);
        this.state = { ...this.state, phones: this.phones.size };
      }
    });
    const hello = acceptFrame(this.state, role, { type: "hello", role });
    this.state = hello.state;
    server.send(JSON.stringify(hello.frame));
    if (role === "phone") {
      for (const event of catchUp(this.state)) server.send(JSON.stringify(event));
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  private async onMessage(role: "pc" | "phone", device: string, raw: string): Promise<void> {
    let frame: Frame;
    try {
      frame = JSON.parse(raw) as Frame;
    } catch {
      return;
    }
    const before = this.state.queue;
    const decision = acceptFrame(this.state, role, frame);
    this.state = decision.state;
    if (this.state.queue !== before) await this.persist();
    if (decision.deliver === "pc") this.pc?.send(JSON.stringify(decision.frame));
    if (decision.deliver === "phones") this.broadcast(decision.frame);
    if (decision.deliver === "sender") {
      const socket = role === "pc" ? this.pc : this.phones.get(device);
      socket?.send(JSON.stringify(decision.frame));
    }
    if (frame.type === "event" && this.phones.size === 0) await this.pushFcm(frame);
  }

  private broadcast(frame: Frame): void {
    const raw = JSON.stringify(frame);
    for (const socket of this.phones.values()) socket.send(raw);
  }

  private async pushFcm(frame: Frame): Promise<void> {
    if (!this.env.FCM_SERVER_KEY) return;
    for (const token of this.fcmTokens) {
      await fetch(`https://fcm.googleapis.com/v1/projects/${this.env.FCM_PROJECT || "orion"}/messages:send`, {
        method: "POST",
        headers: { Authorization: `Bearer ${this.env.FCM_SERVER_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ message: fcmBody(token, frame) }),
      });
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const account = url.searchParams.get("account") || "";
    const role = parseRole(url.searchParams.get("role"));
    const token = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/, "");
    if (!role || !(await verifyRelayToken(env.RELAY_SECRET, account, role, token))) {
      return new Response("Not authorised for this account.", { status: 401 });
    }
    const room = env.ROOM.get(env.ROOM.idFromName(account));
    return room.fetch(request);
  },
};
