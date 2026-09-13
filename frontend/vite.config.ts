import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

declare const process: { env: Record<string, string | undefined> };

const apiTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "BioTwin · Beyond Numbers",
        short_name: "BioTwin",
        description: "Wearables give you numbers. BioTwin gives you understanding.",
        theme_color: "#101515",
        background_color: "#101515",
        display: "standalone",
        start_url: "/",
        id: "/",
        scope: "/",
        icons: [
          {
            src: "/icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        maximumFileSizeToCacheInBytes: 20000000,
        globPatterns: [
          "**/*.{js,css,html,svg,png,json,woff2,hdr}",
          "assets/model.glb",
        ],
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/auth\//,
          /^\/webhooks\//,
          /^\/ops\//,
        ],
        // Health API responses are deliberately never cached by the service worker.
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    // Bind all interfaces, not just loopback, so teammates on the same
    // WiFi can open http://<this machine's LAN IP>:5173 (see README).
    host: true,
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/auth": apiTarget,
      "/sources": apiTarget,
      "/ops": apiTarget,
      "/ws": { target: wsTarget, ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei"],
          charts: ["recharts"],
        },
      },
    },
  },
});
