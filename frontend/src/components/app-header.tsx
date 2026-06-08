import Link from "next/link";
import { Radar } from "lucide-react";

interface AppHeaderProps {
  subtitle?: string;
}

export function AppHeader({ subtitle }: AppHeaderProps) {
  return (
    <header className="border-b border-zinc-800/60 bg-zinc-950/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <Link href="/" className="group flex items-center gap-3">
          <div className="relative flex h-8 w-8 items-center justify-center">
            <div className="absolute inset-0 rounded-lg border border-cyan-500/30" />
            <Radar className="h-4 w-4 text-cyan-400" aria-hidden="true" />
            <div className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-cyan-400 animate-signal-blink" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-zinc-100">
              面经雷达
            </h1>
            <p className="text-[11px] text-zinc-600 group-hover:text-zinc-500">
              OfferGraph
            </p>
          </div>
        </Link>
        {subtitle && (
          <p className="hidden text-xs text-zinc-500 md:block">{subtitle}</p>
        )}
      </div>
    </header>
  );
}
