import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { adminPlugin } from "../src/admin-api.mjs";

export default defineConfig({
  plugins: [react(), adminPlugin()],
  server: { host: "127.0.0.1", port: 4173, strictPort: true },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
});
