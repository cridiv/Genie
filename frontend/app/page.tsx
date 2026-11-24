import { Button } from "@ui-sdk/react/button";
import { BlurText } from "@/components/react-bits/blur-text";
import { DotGrid } from "@/components/react-bits/dot-grid";
import { SiteNav } from "@/components/site-nav";
import { ArrowRightIcon, SparkleIcon } from "@/components/ui/icons";

export default function HomePage() {
  return (
    <>
      <div className="pointer-events-none fixed inset-0 z-0">
        <DotGrid />
        <div className="absolute inset-0 bg-ink/60 backdrop-blur-[3px]" />
      </div>

      <SiteNav />

      <section className="relative z-10 flex min-h-[80svh] flex-1 flex-col items-center justify-center gap-10 px-6 pt-24 pb-12">
        <h1 className="hero-title max-w-[15ch] text-center text-balance font-display font-bold tracking-tight">
          <BlurText text="Find genuine drugs with Genium" highlight="Genium" />
        </h1>

        <Button className="group flex h-14 items-center gap-3 rounded-pill bg-accent pl-7 pr-2 text-base font-semibold text-accent-ink transition-transform duration-200 ease-out active:scale-[0.97]">
          Start
          <span className="flex h-10 w-10 items-center justify-center rounded-pill bg-ink text-accent transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-active:translate-x-1">
            <ArrowRightIcon className="h-4 w-4" />
          </span>
        </Button>
      </section>

      <footer className="relative z-10 mt-auto flex flex-col items-center gap-5 px-6 pb-[max(2rem,env(safe-area-inset-bottom))]">
        <div className="h-px w-full max-w-[200px] bg-line" />
        <span className="flex h-9 w-9 items-center justify-center rounded-pill border border-line text-muted">
          <SparkleIcon className="h-4 w-4" />
        </span>
      </footer>
    </>
  );
}
