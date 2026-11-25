import type { MetadataRoute } from "next";

const icon = (
  name: string,
  size: number,
  purpose: "any" | "maskable",
): { src: string; sizes: string; type: string; purpose: "any" | "maskable" } => ({
  src: `/icons/${name}`,
  sizes: `${size}x${size}`,
  type: "image/png",
  purpose,
});

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Genium — Verify before you buy",
    short_name: "Genium",
    description:
      "Scan medicines and consumables to check authenticity and find verified pharmacies nearby.",
    id: "/",
    start_url: "/",
    scope: "/",
    lang: "en",
    dir: "ltr",
    display: "standalone",
    display_override: ["standalone", "minimal-ui"],
    orientation: "portrait",
    background_color: "#0b0e13",
    theme_color: "#0b0e13",
    categories: ["health", "medical", "utilities"],
    prefer_related_applications: false,
    icons: [
      icon("icon-192.png", 192, "any"),
      icon("icon-512.png", 512, "any"),
      icon("icon-maskable-192.png", 192, "maskable"),
      icon("icon-maskable-512.png", 512, "maskable"),
      {
        src: "/icons/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
    shortcuts: [
      {
        name: "Scan a product",
        short_name: "Scan",
        url: "/scan",
        icons: [icon("icon-192.png", 192, "any")],
      },
      {
        name: "Verified pharmacies",
        short_name: "Pharmacies",
        url: "/pharmacies",
        icons: [icon("icon-192.png", 192, "any")],
      },
    ],
  };
}
