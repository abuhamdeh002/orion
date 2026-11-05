// Relay tokens: base64url(HMAC-SHA256(RELAY_SECRET, "orion-relay:v1:<account>:<role>")).
// The site mints them after purchase; the relay recomputes and compares in constant time.
// A phone token cannot join as the PC, and neither can join another account's room.

export type Role = "pc" | "phone";

const encoder = new TextEncoder();

function b64url(bytes: ArrayBuffer): string {
  let text = "";
  for (const byte of new Uint8Array(bytes)) text += String.fromCharCode(byte);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function relayToken(secret: string, account: string, role: Role): Promise<string> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(`orion-relay:v1:${account}:${role}`));
  return b64url(mac);
}

function sameText(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return diff === 0;
}

export async function verifyRelayToken(secret: string | undefined, account: string, role: Role, token: string): Promise<boolean> {
  if (!secret || secret.length < 32 || !account || !token) return false;
  return sameText(await relayToken(secret, account, role), token);
}

export function parseRole(value: string | null): Role | null {
  return value === "pc" || value === "phone" ? value : null;
}
