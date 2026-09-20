import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The /binance and /stocks proxies exist only so the display-only chart can
// fetch candles from the browser without tripping CORS. The contract calls the
// origin APIs directly and never sees these paths.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/binance": {
        target: "https://data-api.binance.vision",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/binance/, ""),
      },
      "/stocks": {
        target: "https://stockanalysis.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/stocks/, ""),
      },
    },
  },
});
