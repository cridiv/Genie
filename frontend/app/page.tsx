import { Button } from "@ui-sdk/react/button";
import { BlurText } from "@/components/react-bits/blur-text";
import { DotGrid } from "@/components/react-bits/dot-grid";
import { HeroActions } from "@/components/hero-actions";
import { SiteNav } from "@/components/site-nav";
import { ScanIcon, SparkleIcon, StoreIcon } from "@/components/ui/icons";

export default function HomePage() {
  return (
    <>
      <div className="pointer-events-none fixed inset-0 z-0">
        <DotGrid
          dotSize={4}
          gap={26}
          baseColor="#3a4655"
          activeColor="#c8f65a"
          proximity={110}
          strength={0.9}
          glow={0.5}
          dpr={1.5}
        />
        <div className="absolute inset-0 bg-ink/50 backdrop-blur-[2px]" />
      </div>

      <SiteNav />

      <section className="relative z-10 flex min-h-[80svh] flex-1 flex-col items-center justify-center gap-10 px-6 pt-24 pb-12">
        <h1 className="hero-title max-w-[15ch] text-center text-balance font-display font-bold tracking-tight">
          <BlurText text="Find genuine drugs with Genium" highlight="Genium" />
        </h1>

        <HeroActions />
      </section>

      <footer className="relative z-10 mt-auto px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
        <div className="flex items-end justify-between gap-4 rounded-card border border-line bg-surface/85 p-5 backdrop-blur-md">
          <div className="flex flex-col gap-4">
            <span className="font-display text-[2.6rem] font-extrabold leading-[0.85] tracking-[-0.04em]">
              genium
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-9 rounded-pill bg-accent" />
              <span className="h-1.5 w-4 rounded-pill bg-line" />
              <span className="h-1.5 w-4 rounded-pill bg-line" />
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Button
              aria-label="Scan a product"
              className="flex h-12 w-12 items-center justify-center rounded-pill border border-line bg-card text-fg transition-transform duration-200 ease-out active:scale-95"
            >
              <ScanIcon className="h-5 w-5" />
            </Button>
            <Button
              aria-label="Find a verified pharmacy"
              className="flex h-12 w-12 items-center justify-center rounded-pill bg-accent text-accent-ink transition-transform duration-200 ease-out active:scale-95"
            >
              <StoreIcon className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-center">
          <span className="flex h-9 w-9 items-center justify-center rounded-pill bg-accent text-accent-ink">
            <SparkleIcon className="h-4 w-4" />
          </span>
        </div>
      </footer>
    </>
  );
}
