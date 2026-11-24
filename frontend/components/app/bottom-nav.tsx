"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";
import { HistoryIcon, HomeIcon, ScanIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

function NavItem({
  href,
  label,
  icon: Icon,
  active,
}: {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex flex-1 flex-col items-center gap-1 rounded-pill py-2 text-[11px] font-semibold transition",
        active ? "text-accent" : "text-muted",
      )}
    >
      <Icon className="h-5 w-5" />
      {label}
    </Link>
  );
}

export function BottomNav() {
  const pathname = usePathname();

  // The scan screen is a focused camera view — hide the dock there.
  if (pathname.startsWith("/scan") || pathname.startsWith("/offline")) {
    return null;
  }

  const isScan = pathname.startsWith("/scan");

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40">
      <div className="nav-safe mx-auto w-full max-w-[480px] px-4">
        <div className="pointer-events-auto relative flex items-center rounded-pill border border-line bg-surface px-2 py-1.5">
          <NavItem
            href="/"
            label="Home"
            icon={HomeIcon}
            active={pathname === "/"}
          />
          <div className="w-16 shrink-0" aria-hidden />
          <NavItem
            href="/history"
            label="History"
            icon={HistoryIcon}
            active={pathname.startsWith("/history")}
          />

          <Link
            href="/scan"
            aria-label="Scan a product"
            className={cn(
              "absolute left-1/2 top-0 flex h-16 w-16 -translate-x-1/2 -translate-y-1/3 items-center justify-center rounded-pill bg-accent text-accent-ink transition active:scale-95",
              isScan && "ring-4 ring-accent/20",
            )}
          >
            <ScanIcon className="h-7 w-7" />
          </Link>
        </div>
      </div>
    </div>
  );
}
