import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { RegisterServiceWorker } from "@/components/pwa/register-sw";
import { BottomNav } from "@/components/app/bottom-nav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  applicationName: "Genie",
  title: {
    default: "Genie — Verify before you buy",
    template: "%s · Genie",
  },
  description:
    "Scan medicines and consumables to check authenticity and find verified pharmacies nearby.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Genie",
  },
  formatDetection: { telephone: false },
  icons: {
    icon: "/icons/icon.svg",
    apple: "/icons/icon.svg",
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-dvh">
        <RegisterServiceWorker />
        <div className="relative mx-auto flex min-h-dvh w-full max-w-[480px] flex-col">
          {children}
        </div>
        <BottomNav />
      </body>
    </html>
  );
}
