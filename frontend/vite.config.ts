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
      // Scoped to /chat/stream, not a bare "/chat" -- that's also the
      // frontend's own client-side route for the chat page, and a broad
      // proxy rule would intercept it before Vite/React Router ever see it.
      "/chat/stream": "http://localhost:8010",
      // /people and /people/:id are GET routes that exactly overlap the
      // frontend's own client-side page paths, unlike /repo or /chat/stream.
      // A plain proxy rule would send a hard reload of /people straight to
      // the backend (404) instead of the SPA shell. bypass returning req.url
      // (a no-op) only for real document navigations (Sec-Fetch-Dest:
      // document) lets Vite serve the SPA shell on reload while the
      // frontend's own fetch("/people?...") calls (Sec-Fetch-Dest: empty)
      // still proxy through normally.
      "/people": {
        target: "http://localhost:8010",
        bypass(req) {
          if (req.headers["sec-fetch-dest"] === "document") {
            return req.url
          }
        },
      },
    },
  },
})
