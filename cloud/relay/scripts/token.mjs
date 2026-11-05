// Mint relay tokens for local testing:  RELAY_SECRET=... node scripts/token.mjs <account>
import { createHmac } from "node:crypto";

const secret = process.env.RELAY_SECRET;
const account = process.argv[2];
if (!secret || !account) {
  console.error("Usage: RELAY_SECRET=<secret> node scripts/token.mjs <account>");
  process.exit(1);
}
for (const role of ["pc", "phone"]) {
  const token = createHmac("sha256", secret).update(`orion-relay:v1:${account}:${role}`).digest("base64url");
  console.log(`${role}: ${token}`);
}
