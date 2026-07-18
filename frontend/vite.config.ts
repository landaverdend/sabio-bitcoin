import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Frontend code fetches relative paths (same-origin) rather than a
    // hardcoded backend URL -- this proxy is what makes that work in dev,
    // where frontend and backend are actually two different processes/ports.
    // In production this becomes a non-issue as long as both are served
    // from the same origin (reverse proxy, or the backend serving the built
    // frontend statically).
    proxy: {
      "/repo": "http://localhost:8010",
      "/ping": "http://localhost:8010",
    },
  },
})
