"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, RefreshCw } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { StreamingFeed } from "@/components/streaming-feed";
import { getProfile } from "@/lib/session-storage";
import type { SearchProfile } from "@/lib/types";

export default function FeedPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<SearchProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchKey, setSearchKey] = useState(0);

  useEffect(() => {
    const storedProfile = getProfile();
    if (!storedProfile) { router.replace("/"); return; }
    setProfile(storedProfile);
    setLoading(false);
  }, [router]);

  const handleRefresh = useCallback(() => { setSearchKey((k) => k + 1); }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-500" />
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="搜索结果" />

      <main className="mx-auto max-w-5xl px-6 py-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">实时搜索</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {profile.target_companies.length > 0 && (
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
                  {profile.target_companies.join(" / ")}
                </span>
              )}
              {profile.directions.length > 0 && (
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
                  {profile.directions.join(" / ")}
                </span>
              )}
              {profile.identity === "working_switch" && (
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-500">社招</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs text-zinc-500 transition hover:border-zinc-700 hover:text-zinc-400"
            >
              修改画像
            </Link>
            <button
              onClick={handleRefresh}
              className="inline-flex items-center gap-1.5 rounded-md bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-cyan-500"
            >
              <RefreshCw className="h-3 w-3" />
              重新搜索
            </button>
          </div>
        </div>

        <StreamingFeed
          key={searchKey}
          profile={profile}
          defaultCompany={profile.target_companies[0] ?? ""}
          defaultPosition={profile.directions[0] ?? ""}
        />
      </main>
    </div>
  );
}
