import { cn } from "@/lib/cn";

/**
 * The Genium mark: the front and the back of a pack, fanned like the pair of
 * frames the scan flow captures and the result screen shows.
 *
 * Drawn on the same 32-unit grid as the generated icons, in `currentColor`, so
 * it stays crisp from a 16px favicon to a launcher icon.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden
      focusable="false"
      className={cn("shrink-0", className)}
    >
      <rect
        x={7.1}
        y={5.05}
        width={11}
        height={13.5}
        rx={3.9}
        fill="currentColor"
        fillOpacity={0.42}
        transform="rotate(-12 12.6 11.8)"
      />
      <rect
        x={13.9}
        y={13.45}
        width={11}
        height={13.5}
        rx={3.9}
        fill="currentColor"
        transform="rotate(-12 19.4 20.2)"
      />
    </svg>
  );
}
