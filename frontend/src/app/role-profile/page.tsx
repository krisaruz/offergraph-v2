"use client";

import { type KeyboardEvent, type ReactNode, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  FileText,
  Loader2,
  RadioTower,
  RefreshCw,
  Search,
  ShieldAlert,
  Target,
} from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { searchRoleProfile, toApiError } from "@/lib/api";
import { formatDuration, formatPercent, SOURCE_LABELS } from "@/lib/format";
import type {
  RoleProfileEvidence,
  RoleProfileSearchResponse,
  RoleProfileSkillWeight,
} from "@/lib/types";

const EXAMPLES = [
  "阿里+字节的自动化测试工程师",
  "Kimi 的大模型 Eval 评测方向",
];

type SourceStatusValue =
  | string
  | {
      status: string;
      reason?: string | null;
      nextAction?: string;
      recoverable?: boolean;
      count?: number;
    };

function sourceStatusLabel(value: SourceStatusValue): string {
  return typeof value === "string" ? value : value.status;
}

function sourceStatusReason(value: SourceStatusValue): string | null {
  return typeof value === "string" ? null : value.reason ?? null;
}

function confidenceClass(confidence: string): string {
  if (confidence === "high") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  if (confidence === "medium") return "border-cyan-500/30 bg-cyan-500/10 text-cyan-300";
  return "border-orange-500/30 bg-orange-500/10 text-orange-300";
}

function statusClass(status: string): string {
  if (status === "ok" || status === "success") return "border-emerald-500/30 text-emerald-300";
  if (status === "empty" || status === "partial_success") return "border-cyan-500/30 text-cyan-300";
  if (status === "config_error" || status === "auth_required") return "border-orange-500/30 text-orange-300";
  if (status === "error" || status === "timeout") return "border-red-500/30 text-red-300";
  return "border-zinc-700 text-zinc-400";
}

function evidenceTypeLabel(type: string): string {
  if (type === "jd_fact") return "JD";
  if (type === "interview_evidence") return "面经";
  return type;
}

function Section({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-zinc-800/80 pt-5">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <span className="text-cyan-400">{icon}</span>
        {title}
      </div>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-l border-zinc-800 pl-3">
      <div className="text-[11px] text-zinc-600">{label}</div>
      <div className="mt-1 text-sm font-medium text-zinc-200">{value}</div>
    </div>
  );
}

function SkillBar({ skill }: { skill: RoleProfileSkillWeight }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-4">
        <span className="text-sm text-zinc-200">{skill.skill}</span>
        <span className="font-mono text-xs text-cyan-300">{formatPercent(skill.weight)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-sm bg-zinc-800">
        <div className="h-full rounded-sm bg-cyan-400" style={{ width: `${Math.min(Math.max(skill.weight, 0), 1) * 100}%` }} />
      </div>
      <p className="mt-1 text-xs text-zinc-500">{skill.reason}</p>
    </div>
  );
}

function EvidenceRow({ evidence }: { evidence: RoleProfileEvidence }) {
  const isJob = evidence.evidenceType === "jd_fact";
  return (
    <article className="rounded-md border border-zinc-800/80 bg-zinc-950/50 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className={`rounded-sm border px-2 py-0.5 text-[11px] ${isJob ? "border-cyan-500/30 text-cyan-300" : "border-emerald-500/30 text-emerald-300"}`}>
          {evidenceTypeLabel(evidence.evidenceType)}
        </span>
        <span className="text-xs text-zinc-500">{SOURCE_LABELS[evidence.source] ?? evidence.source}</span>
        <span className="font-mono text-xs text-zinc-600">{formatPercent(evidence.confidence)}</span>
        {evidence.publishedAt && <span className="text-xs text-zinc-600">{evidence.publishedAt}</span>}
      </div>
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-sm font-medium text-zinc-100">{evidence.title ?? "未命名证据"}</h3>
        <Link
          href={evidence.sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-zinc-500 transition hover:text-cyan-300"
          aria-label="打开来源"
        >
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      </div>
      {evidence.quote && (
        <p className="mt-2 border-l border-zinc-700 pl-3 text-sm leading-6 text-zinc-400">
          {evidence.quote}
        </p>
      )}
      {evidence.limitations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {evidence.limitations.map((limitation) => (
            <span key={limitation} className="rounded-sm border border-orange-500/20 px-2 py-0.5 text-[11px] text-orange-300/90">
              {limitation}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

export default function RoleProfilePage() {
  const [keyword, setKeyword] = useState("");
  const [result, setResult] = useState<RoleProfileSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const evidenceGroups = useMemo(() => {
    const evidence = result?.profile.evidence ?? [];
    return {
      jd: evidence.filter((item) => item.evidenceType === "jd_fact"),
      interviews: evidence.filter((item) => item.evidenceType !== "jd_fact"),
    };
  }, [result]);

  async function runSearch(nextKeyword = keyword) {
    const trimmed = nextKeyword.trim();
    if (!trimmed || loading) return;
    setKeyword(trimmed);
    setLoading(true);
    setError(null);
    try {
      const response = await searchRoleProfile({ keyword: trimmed, identity: "working_switch" });
      setResult(response);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Enter") {
      event.preventDefault();
      void runSearch();
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="岗位画像" />
      <main className="relative mx-auto max-w-7xl overflow-x-hidden px-4 py-7 sm:px-6">
        <div className="pointer-events-none fixed inset-0 radar-grid opacity-35" />

        <div className="relative mb-6">
          <div className="mb-4 flex flex-col items-start gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs text-cyan-400">
                <Target className="h-3.5 w-3.5" />
                Role Profile Console
              </div>
              <h2 className="text-2xl font-semibold text-zinc-100">岗位画像雷达</h2>
            </div>
            <Link href="/feed" className="inline-flex max-w-full items-center gap-2 rounded-md border border-zinc-800 px-3 py-2 text-sm text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-200">
              <RadioTower className="h-4 w-4" />
              实时 Feed
            </Link>
          </div>

          <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/50 p-4">
            <div className="flex flex-col gap-3 lg:flex-row">
              <label className="flex min-w-0 flex-1 items-center gap-3 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2.5 focus-within:border-cyan-500/60">
                <Search className="h-4 w-4 shrink-0 text-zinc-500" />
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="阿里+字节的自动化测试工程师"
                  className="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
                  disabled={loading}
                />
              </label>
              <button
                onClick={() => void runSearch()}
                disabled={loading || keyword.trim().length < 2}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-cyan-600 px-5 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 lg:w-auto"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BrainCircuit className="h-4 w-4" />}
                {loading ? "分析中" : "生成岗位画像"}
              </button>
            </div>
            <div className="mt-3 grid gap-2 sm:flex sm:flex-wrap">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => void runSearch(example)}
                  disabled={loading}
                  className="w-full truncate rounded-sm border border-zinc-800 px-2.5 py-1 text-left text-xs text-zinc-500 transition hover:border-cyan-500/40 hover:text-cyan-300 disabled:opacity-50 sm:w-auto"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="relative mb-5 rounded-lg border border-red-500/30 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="font-medium">画像生成失败</p>
                <p className="mt-1 text-red-200/80">{error}</p>
              </div>
              <button
                onClick={() => void runSearch()}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-md border border-red-500/30 px-2.5 py-1 text-xs text-red-100 transition hover:bg-red-500/10"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                重试
              </button>
            </div>
          </div>
        )}

        {loading && !result && (
          <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]" role="status">
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-6">
              <div className="mb-5 h-5 w-48 animate-pulse rounded-sm bg-zinc-800" />
              <div className="space-y-3">
                <div className="h-3 w-full animate-pulse rounded-sm bg-zinc-800/80" />
                <div className="h-3 w-11/12 animate-pulse rounded-sm bg-zinc-800/70" />
                <div className="h-3 w-8/12 animate-pulse rounded-sm bg-zinc-800/60" />
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-5">
              <Loader2 className="mb-3 h-5 w-5 animate-spin text-cyan-400" />
              <p className="text-sm text-zinc-400">正在聚合 JD、面经与来源状态</p>
            </div>
          </div>
        )}

        {!loading && !result && !error && (
          <div className="relative rounded-lg border border-zinc-800/80 bg-zinc-900/35 p-8 text-center">
            <FileText className="mx-auto mb-4 h-8 w-8 text-zinc-600" />
            <p className="text-sm text-zinc-400">等待岗位关键词</p>
            <p className="mt-1 text-xs text-zinc-600">JD、面经、来源状态和证据限制会在这里汇总。</p>
          </div>
        )}

        {result && (
          <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="space-y-5 rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <span className={`rounded-sm border px-2 py-0.5 text-xs ${confidenceClass(result.profile.confidence)}`}>
                      {result.profile.confidence}
                    </span>
                    <span className="rounded-sm border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400">
                      {formatDuration(result.searchDuration)}
                    </span>
                  </div>
                  <h2 className="text-xl font-semibold text-zinc-100">{result.profile.targetRole}</h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">{result.profile.roleSummary}</p>
                </div>
              </div>

              <Section title="业务场景" icon={<RadioTower className="h-4 w-4" />}>
                <div className="flex flex-wrap gap-2">
                  {result.profile.businessScenarios.map((scenario) => (
                    <span key={scenario} className="rounded-sm border border-zinc-800 bg-zinc-950/60 px-2.5 py-1 text-xs text-zinc-300">
                      {scenario}
                    </span>
                  ))}
                </div>
              </Section>

              <Section title="技能权重" icon={<BarChart3 className="h-4 w-4" />}>
                <div className="grid gap-4 md:grid-cols-2">
                  {result.profile.skillWeights.map((skill) => (
                    <SkillBar key={skill.skill} skill={skill} />
                  ))}
                </div>
              </Section>

              <Section title="面试重点" icon={<Target className="h-4 w-4" />}>
                <ol className="space-y-2">
                  {result.profile.interviewFocus.map((focus, index) => (
                    <li key={`${focus}-${index}`} className="flex gap-3 text-sm leading-6 text-zinc-300">
                      <span className="font-mono text-xs text-cyan-400">{String(index + 1).padStart(2, "0")}</span>
                      <span>{focus}</span>
                    </li>
                  ))}
                </ol>
              </Section>

              <Section title="准备计划" icon={<CheckCircle2 className="h-4 w-4" />}>
                <div className="space-y-3">
                  {result.profile.preparationPlan.map((item, index) => (
                    <div key={`${item.priority}-${index}`} className="grid gap-3 rounded-md border border-zinc-800/80 bg-zinc-950/40 p-3 md:grid-cols-[64px_minmax(0,1fr)]">
                      <span className="font-mono text-sm text-cyan-300">{item.priority}</span>
                      <div>
                        <p className="text-sm font-medium text-zinc-100">{item.action}</p>
                        <p className="mt-1 text-xs leading-5 text-zinc-500">{item.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>

              <Section title="证据链" icon={<FileText className="h-4 w-4" />}>
                {result.profile.evidence.length === 0 ? (
                  <div className="rounded-md border border-orange-500/30 bg-orange-950/10 p-4 text-sm text-orange-200">
                    当前画像没有可展示证据。
                  </div>
                ) : (
                  <div className="space-y-4">
                    {evidenceGroups.jd.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-xs text-zinc-500">JD 证据</p>
                        {evidenceGroups.jd.map((item) => (
                          <EvidenceRow key={`${item.source}-${item.sourceUrl}`} evidence={item} />
                        ))}
                      </div>
                    )}
                    {evidenceGroups.interviews.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-xs text-zinc-500">面经证据</p>
                        {evidenceGroups.interviews.map((item) => (
                          <EvidenceRow key={`${item.source}-${item.sourceUrl}`} evidence={item} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </Section>
            </div>

            <aside className="space-y-5">
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-medium text-zinc-200">
                  <BrainCircuit className="h-4 w-4 text-cyan-400" />
                  解析结果
                </div>
                <div className="space-y-4">
                  <Metric label="公司" value={result.parsedQuery.companies.join(" / ") || "未识别"} />
                  <Metric label="方向" value={result.parsedQuery.directions.join(" / ")} />
                  <Metric label="会话" value={<span className="font-mono text-xs">{result.sessionId || "instant"}</span>} />
                </div>
              </div>

              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-medium text-zinc-200">
                  <BarChart3 className="h-4 w-4 text-cyan-400" />
                  质量统计
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <Metric label="JD" value={String(result.profile.evidenceStats.jobPostingCount ?? 0)} />
                  <Metric label="实时 JD" value={String(result.profile.evidenceStats.liveJobPostingCount ?? 0)} />
                  <Metric label="JobRadar" value={String(result.profile.evidenceStats.localJobRadarEvidenceCount ?? result.qualityReport.localJobRadarEvidenceCount ?? 0)} />
                  <Metric label="面经" value={String(result.profile.evidenceStats.interviewEvidenceCount ?? 0)} />
                </div>
              </div>

              <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-medium text-zinc-200">
                  <ShieldAlert className="h-4 w-4 text-cyan-400" />
                  来源状态
                </div>
                <div className="space-y-2">
                  {Object.entries(result.sourcesStatus).map(([source, value]) => {
                    const status = sourceStatusLabel(value);
                    const reason = sourceStatusReason(value);
                    return (
                      <div key={source} className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm text-zinc-300">{SOURCE_LABELS[source] ?? source}</span>
                          <span className={`rounded-sm border px-2 py-0.5 text-[11px] ${statusClass(status)}`}>{status}</span>
                        </div>
                        {reason && <p className="mt-1 text-xs leading-5 text-zinc-600">{reason}</p>}
                      </div>
                    );
                  })}
                </div>
              </div>

              {result.profile.limitations.length > 0 && (
                <div className="rounded-lg border border-orange-500/30 bg-orange-950/10 p-5">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-orange-200">
                    <AlertCircle className="h-4 w-4" />
                    限制项
                  </div>
                  <ul className="space-y-2">
                    {result.profile.limitations.map((limitation) => (
                      <li key={limitation} className="text-sm leading-6 text-orange-100/80">
                        {limitation}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
