import Link from "next/link";
import { Building2, MapPin, Pencil, Target, User } from "lucide-react";
import { IDENTITY_LABELS } from "@/lib/format";
import type { SearchProfile } from "@/lib/types";

interface ProfileSummaryProps {
  profile: SearchProfile;
  compact?: boolean;
}

export function ProfileSummary({ profile, compact = false }: ProfileSummaryProps) {
  return (
    <div
      className={`rounded-md border border-zinc-800/60 bg-zinc-900/30 ${
        compact ? "p-3" : "p-4"
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-mono text-xs tracking-wider text-zinc-500 uppercase">
          Search Profile
        </h3>
        <Link
          href="/"
          className="inline-flex items-center gap-1 font-mono text-[10px] text-cyan-500 hover:text-cyan-400"
        >
          <Pencil className="h-3 w-3" />
          edit
        </Link>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2 text-zinc-400">
          <User className="h-3.5 w-3.5 shrink-0 text-zinc-600" />
          <span className="font-mono text-xs">{IDENTITY_LABELS[profile.identity]}</span>
        </div>

        <div className="flex items-start gap-2 text-zinc-400">
          <Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-600" />
          <div className="flex flex-wrap gap-1.5">
            {profile.target_companies.map((company) => (
              <Link
                key={company}
                href={`/company/${encodeURIComponent(company)}`}
                className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 transition hover:bg-cyan-500/10 hover:text-cyan-300"
              >
                {company}
              </Link>
            ))}
          </div>
        </div>

        <div className="flex items-start gap-2 text-zinc-400">
          <Target className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-600" />
          <div className="flex flex-wrap gap-1.5">
            {profile.directions.map((dir) => (
              <span
                key={dir}
                className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400"
              >
                {dir}
              </span>
            ))}
          </div>
        </div>

        {profile.regions.length > 0 && (
          <div className="flex items-start gap-2 text-zinc-400">
            <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-600" />
            <div className="flex flex-wrap gap-1.5">
              {profile.regions.map((region) => (
                <span
                  key={region}
                  className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400"
                >
                  {region}
                </span>
              ))}
            </div>
          </div>
        )}

        {profile.custom_needs && !compact && (
          <p className="rounded border border-zinc-800/40 bg-zinc-900/40 px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-500">
            {profile.custom_needs}
          </p>
        )}
      </div>
    </div>
  );
}
