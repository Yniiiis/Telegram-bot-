import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// GitHub Pages project site: set VITE_BASE_PATH=/repo-name/ (e.g. /Telegram-bot-/)
const base = (process.env.VITE_BASE_PATH || "/").replace(/\/?$/, "/");

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
