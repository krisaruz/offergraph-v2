"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  BarChart3,
  Building2,
  HelpCircle,
  Loader2,
  Star,
  TrendingUp,
} from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { CategoryChart } from "@/components/category-chart";
import { TagsCloud } from "@/components/tags-cloud";
import { getCompanyProfile, toApiError } from "@/lib/api";
import { CATEGORY_LABELS, SOURCE_LABELS } from "@/lib/format";
import type { CompanyProfile, HighFreqQuestion } from "@/lib/types";

function DifficultyDisplay({ value }: { value?: number | null }) {
  if (value == null) return <span className="text-zinc-500">—</span>;
  const rounded = Math.round(value * 10) / 10;
  return (
    <span className="inline-flex items-center gap-1">
      <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
      {rounded} / 5
    </span>
  );
}

function QuestionList({ questions }: { questions: HighFreqQuestion[] }) {
  if (questions.length === 0) {
    return <p className="text-sm text-zinc-500">暂无高频问题数据</p>;
  }

  return (
    <div className="space-y-3">
      {questions.slice(0, 15).map((q, index) => (
        <div
          key={`${q.text}-${index}`}
          className="flex items-start gap-4 rounded border border-zinc-800/40 bg-zinc-900/20 px-3 py-2.5"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-xs font-semibold text-zinc-500">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-zinc-200">{q.text}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
              <span className="text-cyan-400">出现 {q.frequency} 次</span>
              {q.category && (
                <span className="rounded bg-zinc-800 px-1.5 py-0.5">
                  {CATEGORY_LABELS[q.category] ?? q.category}
                </span>
              )}
              {q.avgDifficulty != null && (
                <span>难度 {q.avgDifficulty}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SourcesDistribution({
  distribution,
}: {
  distribution: Record<string, number>;
}) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, c]) => sum + c, 0);

  if (entries.length === 0) {
    return <p className="text-sm text-zinc-500">暂无来源分布数据</p>;
  }

  return (
    <div className="space-y-3">
      {entries.map(([source, count]) => (
        <div key={source} className="flex items-center justify-between text-sm">
          <span className="text-zinc-300">
            {SOURCE_LABELS[source] ?? source}
          </span>
          <span className="text-zinc-500">
            {count} ({Math.round((count / total) * 100)}%)
          </span>
        </div>
      ))}
    </div>
  );
}

export default function CompanyProfilePage() {
  const params = useParams();
  const companyName = decodeURIComponent(params.name as string);
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyName) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getCompanyProfile(companyName);
        if (!cancelled) setProfile(data);
      } catch (err) {
        if (!cancelled) setError(toApiError(err).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [companyName]);

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AppHeader />
        <div className="flex items-center justify-center py-32">
          <Loader2 className="h-6 w-6 animate-spin text-cyan-500" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AppHeader />
        <div className="mx-auto max-w-2xl px-6 py-20 text-center">
          <h2 className="mb-2 font-mono text-sm text-zinc-300">
            Failed to load
          </h2>
          <p className="mb-6 font-mono text-xs text-zinc-600">{error}</p>
          <Link
            href="/feed"
            className="inline-flex items-center gap-2 rounded-md border border-zinc-800 px-4 py-2 font-mono text-xs text-zinc-400 hover:border-zinc-700 hover:text-zinc-300"
          >
            <ArrowLeft className="h-4 w-4" />
            返回
          </Link>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  const sampleCount =
    profile.sampleCount ?? profile.eventCount ?? profile.questionCount ?? 0;
  const difficultyAvg = profile.difficultyAvg ?? profile.avgDifficulty;
  const topQuestions =
    profile.topQuestions?.map((q) => ({
      text: q.text,
      frequency: q.frequency,
      category: null,
      avgDifficulty: null,
      tags: [],
    })) ??
    profile.highFreqQuestions ??
    [];
  const topTags =
    profile.topTags ??
    topQuestions.flatMap((q) => q.tags ?? []).filter(Boolean);
  const hasSufficientData = profile.sufficient_data !== false;

  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="公司面试画像" />

      <main className="mx-auto max-w-6xl px-6 py-8">
        <Link
          href="/feed"
          className="mb-6 inline-flex items-center gap-2 text-sm text-zinc-500 transition hover:text-cyan-400"
        >
          <ArrowLeft className="h-4 w-4" />
          返回搜索结果
        </Link>

        <header className="mb-8 rounded-md border border-zinc-800/60 bg-zinc-900/30 p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-md border border-zinc-800/40">
              <Building2 className="h-6 w-6 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-zinc-50 md:text-3xl">
                {profile.company}
              </h1>
              {profile.position && (
                <p className="mt-1 text-zinc-400">{profile.position}</p>
              )}
              {profile.styleSummary && (
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-500">
                  {profile.styleSummary}
                </p>
              )}
            </div>
          </div>
        </header>

        {!hasSufficientData ? (
          <div className="flex flex-col items-center rounded-md border border-dashed border-zinc-800 px-6 py-16 text-center">
            <HelpCircle className="mb-4 h-10 w-10 text-zinc-700" />
            <h3 className="mb-2 text-sm text-zinc-400">
              数据不足
            </h3>
            <p className="max-w-md text-sm text-zinc-500">
              {profile.message ??
                `当前仅有 ${sampleCount} 条高可信面经，尚不足以生成完整公司画像。请先搜索更多相关面经。`}
            </p>
            <Link
              href="/"
              className="mt-6 inline-flex items-center gap-2 rounded-md bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500"
            >
              开始搜索
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-4">
                <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                  <TrendingUp className="h-3 w-3" />
                  样本数量
                </div>
                <p className="text-xl font-bold text-zinc-100">{sampleCount}</p>
                {profile.questionCount != null && (
                  <p className="mt-1 text-xs text-zinc-500">
                    含 {profile.questionCount} 道真实问题
                  </p>
                )}
              </div>
              <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-4">
                <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                  <Star className="h-3 w-3" />
                  平均难度
                </div>
                <p className="text-xl font-bold text-amber-400">
                  <DifficultyDisplay value={difficultyAvg} />
                </p>
              </div>
              <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-4">
                <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                  <BarChart3 className="h-3 w-3" />
                  证据覆盖率
                </div>
                <p className="text-xl font-bold text-cyan-400">
                  {profile.evidenceCoverageAvg != null
                    ? `${Math.round(profile.evidenceCoverageAvg * 100)}%`
                    : "—"}
                </p>
              </div>
              <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-4">
                <div className="mb-1 text-xs text-zinc-500">高频问题数</div>
                <p className="text-xl font-bold text-zinc-100">
                  {topQuestions.length}
                </p>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <section className="rounded-md border border-zinc-800/60 bg-zinc-900/20 p-5">
                <h2 className="mb-4 text-sm font-semibold text-zinc-200">
                  高频面试题
                </h2>
                <QuestionList questions={topQuestions} />
              </section>

              <div className="space-y-6">
                <section className="rounded-md border border-zinc-800/60 bg-zinc-900/20 p-5">
                  <h2 className="mb-4 text-sm font-semibold text-zinc-200">
                    题目分类分布
                  </h2>
                  <CategoryChart
                    distribution={profile.categoryDistribution ?? {}}
                    variant="pie"
                  />
                </section>

                {profile.sourcesDistribution &&
                  Object.keys(profile.sourcesDistribution).length > 0 && (
                    <section className="rounded-md border border-zinc-800/60 bg-zinc-900/20 p-5">
                      <h2 className="mb-4 text-sm font-semibold text-zinc-200">
                        来源分布
                      </h2>
                      <SourcesDistribution
                        distribution={profile.sourcesDistribution}
                      />
                    </section>
                  )}
              </div>
            </div>

            {topTags.length > 0 && (
              <section className="mt-6 rounded-md border border-zinc-800/60 bg-zinc-900/20 p-5">
                <h2 className="mb-4 text-sm font-semibold text-zinc-200">
                  热门标签
                </h2>
                <TagsCloud tags={topTags} />
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
