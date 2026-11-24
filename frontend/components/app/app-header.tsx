import type { ReactNode } from "react";
import { BackButton } from "./back-button";

export function AppHeader({
  title,
  subtitle,
  right,
  back = true,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  back?: boolean;
}) {
  return (
    <header className="flex items-center gap-3 pt-1">
      {back ? <BackButton /> : <span className="h-10 w-10 shrink-0" />}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{title}</p>
        {subtitle && (
          <p className="truncate text-xs text-muted">{subtitle}</p>
        )}
      </div>
      {right ?? <span className="h-10 w-10 shrink-0" />}
    </header>
  );
}
