import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "BioTwin · Your recovery, understood",
        short_name: "BioTwin",
        description: "Your personal wearable recovery twin",
        theme_color: "#173f39",
        background_color: "#f5f6f2",
        display: "standalone",
        start_url: "/",
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any",
          },
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        maximumFileSizeToCacheInBytes: 8000000,
        globPatterns: ["**/*.{js,css,html,svg,glb,json,woff2}"],
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
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/sources": "http://127.0.0.1:8000",
      "/ops": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
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
