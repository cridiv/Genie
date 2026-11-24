"use client";

import { useRouter } from "next/navigation";
import { ChevronLeftIcon } from "@/components/ui/icons";

export function BackButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.back()}
      aria-label="Go back"
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-pill border border-line bg-card text-fg transition active:scale-95"
    >
      <ChevronLeftIcon />
    </button>
  );
}
