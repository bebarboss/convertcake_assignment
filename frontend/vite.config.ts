import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";

export default defineConfig({
  plugins: [
    tanstackStart({ server: { entry: "server" } }),
    react(),
    tailwindcss(),
    tsconfigPaths(),
  ],
  // Dev only: mirror the Vercel proxy functions in api/ (vite dev doesn't run them)
  server: {
    proxy: {
      "/api": {
        target: process.env.API_BASE ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        headers: { "ngrok-skip-browser-warning": "true" },
      },
    },
  },
});
