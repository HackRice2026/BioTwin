import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Garmin Health Dashboard",
    short_name: "Garmin Health",
    description: "Your health data, one glance at a time.",
    start_url: "/",
    display: "standalone",
    background_color: "#f9f8f3",
    theme_color: "#f9f8f3",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}
