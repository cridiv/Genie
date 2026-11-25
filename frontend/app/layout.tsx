import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Suspense } from "react";
import "./globals.css";
import { RouteProgress } from "@/components/app/route-progress";
import { RegisterServiceWorker } from "@/components/pwa/register-sw";

const bricolage = localFont({
  src: [
    {
      path: "../node_modules/@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2",
      weight: "400 800",
      style: "normal",
    },
  ],
  variable: "--font-bricolage",
  display: "swap",
});

const dmSans = localFont({
  src: [
    {
      path: "../node_modules/@fontsource-variable/dm-sans/files/dm-sans-latin-wght-normal.woff2",
      weight: "400 600",
      style: "normal",
    },
  ],
  variable: "--font-dm-sans",
  display: "swap",
});

export const metadata: Metadata = {
  applicationName: "Genium",
  title: {
    default: "Genium — Verify before you buy",
    template: "%s · Genium",
  },
  description:
    "Scan medicines and consumables to check authenticity and find verified pharmacies nearby.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Genium",
  },
  formatDetection: { telephone: false },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icons/icon.svg", type: "image/svg+xml", sizes: "any" },
      { url: "/icons/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/icons/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: [
      {
        url: "/icons/apple-touch-icon.png",
        type: "image/png",
        sizes: "180x180",
      },
    ],
  },
};

export const viewport: Viewport = {
  themeColor: "#0b0e13",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${dmSans.variable} h-full antialiased`}
    >
      <body className="min-h-dvh">
        <RegisterServiceWorker />
        <Suspense fallback={null}>
          <RouteProgress />
        </Suspense>
        <div className="relative mx-auto flex min-h-dvh w-full max-w-[480px] flex-col">
          {children}
        </div>
      </body>
    </html>
  );
}
