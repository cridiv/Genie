import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Screen({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <main className={cn("screen-pad flex flex-1 flex-col gap-5 px-5", className)}>
      {children}
    </main>
  );
}
