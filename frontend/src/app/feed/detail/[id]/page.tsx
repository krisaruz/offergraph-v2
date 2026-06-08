"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Building2, ExternalLink, Loader2, MapPin, Users } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { QuestionCard } from "@/components/question-card";
import { TrustBadge } from "@/components/trust-badge";
import { getFeedDetail, toApiError } from "@/lib/api";
import { formatDate, formatPercent, SOURCE_LABELS } from "@/lib/format";
import type { FeedDetailResponse } from "@/lib/types";

export default function FeedDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [detail, setDetail] = useState<FeedDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      setLoading(true); setError(null);
      try {
        const data = await getFeedDetail(id);
        if (!cancelled) setDetail(data);
      } catch (err) {
        if (!cancelled) setError(toApiError(err).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

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

  if (error || !detail) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AppHeader />
        <div className="mx-auto max-w-2xl px-6 py-20 text-center">
          <h2 className="mb-2 text-lg font-semibold text-zinc-100">加载详情失败</h2>
          <p className="mb-6 text-sm text-zinc-500">{error ?? "未找到该面经详情"}</p>
          <Link href="/feed" className="inline-flex items-center gap-2 rounded-md border border-zinc-800 px-4 py-2 text-sm text-zinc-400 hover:border-zinc-700 hover:text-zinc-300">
            <ArrowLeft className="h-4 w-4" />返回列表
          </Link>
        </div>
      </div>
    );
  }

  const events = detail.structured?.events ?? [];
  const totalQuestions = events.reduce((sum, e) => sum + (e.questions?.length ?? 0), 0);

  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="面经详情" />
      <main className="mx-auto max-w-4xl px-6 py-6">
        <Link href="/feed" className="mb-5 inline-flex items-center gap-2 text-sm text-zinc-500 transition hover:text-cyan-400">
          <ArrowLeft className="h-4 w-4" />返回搜索结果
        </Link>

        <header className="mb-6 rounded-md border border-zinc-800/60 bg-zinc-900/30 p-5">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-zinc-100">{detail.title ?? "面经详情"}</h1>
              <p className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-zinc-600">
                <span>{SOURCE_LABELS[detail.source] ?? detail.source}</span>
                {detail.fetchedAt && <span>抓取于 {formatDate(detail.fetchedAt)}</span>}
              </p>
            </div>
            {detail.extractionConfidence != null && (
              <TrustBadge label={detail.extractionConfidence >= 0.8 ? "high" : detail.extractionConfidence >= 0.5 ? "medium" : "low"} />
            )}
          </div>
          {detail.snippet && <p className="mb-3 text-sm leading-relaxed text-zinc-500">{detail.snippet}</p>}
          <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-600">
            <span>{events.length} 场面试 · {totalQuestions} 道问题</span>
            {detail.extractionConfidence != null && <span>置信度 {formatPercent(detail.extractionConfidence)}</span>}
            {detail.sourceUrl && (
              <a href={detail.sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-cyan-500 hover:text-cyan-400">
                <ExternalLink className="h-3 w-3" />查看原文
              </a>
            )}
          </div>
        </header>

        {events.length === 0 ? (
          <div className="rounded-md border border-dashed border-zinc-800 px-6 py-16 text-center">
            <p className="text-sm text-zinc-600">该面经尚未完成结构化抽取，请稍后重试或查看原文链接</p>
          </div>
        ) : (
          <div className="space-y-6">
            {events.map((event) => (
              <section key={event.id} className="rounded-md border border-zinc-800/60 bg-zinc-900/20 p-5">
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  {event.company && (
                    <Link href={`/company/${encodeURIComponent(event.company)}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-cyan-400 hover:text-cyan-300">
                      <Building2 className="h-4 w-4" />{event.company}
                    </Link>
                  )}
                  {event.position && <span className="text-sm text-zinc-400">{event.position}</span>}
                  {event.round && <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-500">{event.round}</span>}
                  {event.region && <span className="inline-flex items-center gap-1 text-xs text-zinc-600"><MapPin className="h-3 w-3" />{event.region}</span>}
                  {event.candidateType && <span className="inline-flex items-center gap-1 text-xs text-zinc-600"><Users className="h-3 w-3" />{event.candidateType}</span>}
                </div>
                {event.summary && <p className="mb-4 rounded border border-zinc-800/40 bg-zinc-900/40 px-4 py-3 text-sm leading-relaxed text-zinc-400">{event.summary}</p>}
                {event.tags && event.tags.length > 0 && (
                  <div className="mb-4 flex flex-wrap gap-1.5">
                    {event.tags.map((tag) => <span key={tag} className="rounded bg-cyan-500/10 px-1.5 py-0.5 text-xs text-cyan-400">{tag}</span>)}
                  </div>
                )}
                <div className="space-y-3">
                  {event.questions.map((question, index) => <QuestionCard key={question.id} question={question} index={index} />)}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
