"use client";

import { useMemo } from "react";
import {
  BarChart3,
  ChevronDown,
  ChevronUp,
  FileText,
  Hash,
  MessageSquare,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import type { FeedItem, FeedQuestionPreview } from "@/lib/types";
import { CATEGORY_LABELS, SOURCE_LABELS } from "@/lib/format";

/**
 * 面经汇总面板 — 搜索完成后展示结构化统计。
 *
 * 设计意图：Editorial Data Product 风格。
 * 基于前端已有的 FeedItem[] 数据聚合计算，不新增后端 API。
 * 汇总内容：概览统计、高频问题、问题分类分布、来源分布。
 */

interface FeedSummaryProps {
  items: FeedItem[];
  searching: boolean;
  enhancing: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

interface AggregatedQuestion {
  text: string;
  category: string | null;
  frequency: number;
  avgDifficulty: number | null;
  hasEvidence: boolean;
}

function aggregateQuestions(items: FeedItem[]): AggregatedQuestion[] {
  const questionMap = new Map<string, {
    text: string;
    category: string | null;
    count: number;
    difficulties: number[];
    hasEvidence: boolean;
  }>();

  for (const item of items) {
    const questions = item.representative_questions ?? [];
    for (const q of questions) {
      // 用文本前80字符做去重 key（忽略末尾标点差异）
      const key = q.text.trim().slice(0, 80).replace(/[？?。.]+$/, "").toLowerCase();
      if (!key) continue;

      const existing = questionMap.get(key);
      if (existing) {
        existing.count++;
        if (q.difficulty != null) existing.difficulties.push(q.difficulty);
        if (q.evidence_quote) existing.hasEvidence = true;
      } else {
        questionMap.set(key, {
          text: q.text,
          category: q.category ?? null,
          count: 1,
          difficulties: q.difficulty != null ? [q.difficulty] : [],
          hasEvidence: !!q.evidence_quote,
        });
      }
    }
  }

  return Array.from(questionMap.values())
    .map((entry) => ({
      text: entry.text,
      category: entry.category,
      frequency: entry.count,
      avgDifficulty:
        entry.difficulties.length > 0
          ? Math.round((entry.difficulties.reduce((a, b) => a + b, 0) / entry.difficulties.length) * 10) / 10
          : null,
      hasEvidence: entry.hasEvidence,
    }))
    .sort((a, b) => b.frequency - a.frequency);
}

function aggregateCategories(items: FeedItem[]): Array<{ category: string; label: string; count: number }> {
  const categoryMap = new Map<string, number>();

  for (const item of items) {
    const questions = item.representative_questions ?? [];
    for (const q of questions) {
      const cat = q.category || "other";
      categoryMap.set(cat, (categoryMap.get(cat) ?? 0) + 1);
    }
  }

  return Array.from(categoryMap.entries())
    .map(([category, count]) => ({
      category,
      label: CATEGORY_LABELS[category] ?? category,
      count,
    }))
    .sort((a, b) => b.count - a.count);
}

function aggregateSources(items: FeedItem[]): Array<{ source: string; label: string; count: number }> {
  const sourceMap = new Map<string, number>();

  for (const item of items) {
    sourceMap.set(item.source, (sourceMap.get(item.source) ?? 0) + 1);
  }

  return Array.from(sourceMap.entries())
    .map(([source, count]) => ({
      source,
      label: SOURCE_LABELS[source] ?? source,
      count,
    }))
    .sort((a, b) => b.count - a.count);
}

export function FeedSummary({ items, searching, enhancing, collapsed, onToggleCollapse }: FeedSummaryProps) {
  const isComplete = !searching;
  const hasItems = items.length > 0;

  const totalQuestions = useMemo(
    () => items.reduce((sum, item) => sum + (item.question_count ?? 0), 0),
    [items],
  );

  const topQuestions = useMemo(() => aggregateQuestions(items).slice(0, 8), [items]);
  const categories = useMemo(() => aggregateCategories(items), [items]);
  const sources = useMemo(() => aggregateSources(items), [items]);

  const avgEvidence = useMemo(() => {
    const values = items
      .map((item) => item.evidence_coverage)
      .filter((v): v is number => v != null);
    return values.length > 0
      ? Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100)
      : null;
  }, [items]);

  const maxCategoryCount = useMemo(
    () => Math.max(...categories.map((c) => c.count), 1),
    [categories],
  );

  // 搜索进行中且无结果时不渲染
  if (!hasItems && searching) return null;
  // 搜索完成且无结果时不渲染
  if (!hasItems && !searching) return null;

  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      {/* 头部：可折叠 */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-slate-50/50"
      >
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100 text-slate-600">
            <BarChart3 className="h-3.5 w-3.5" />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">面经汇总</h3>
            <p className="text-[11px] text-slate-500">
              {isComplete ? `${items.length} 篇面经 · ${totalQuestions} 道问题` : "搜索进行中..."}
              {enhancing && " · 深度分析中"}
            </p>
          </div>
        </div>
        {collapsed ? (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {!collapsed && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3">
          {/* 概览统计 */}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard icon={FileText} label="面经篇数" value={items.length} />
            <StatCard icon={MessageSquare} label="问题总数" value={totalQuestions} />
            <StatCard icon={Hash} label="数据源" value={sources.length} />
            <StatCard
              icon={ShieldCheck}
              label="证据覆盖"
              value={avgEvidence != null ? `${avgEvidence}%` : "-"}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* 高频问题 */}
            {topQuestions.length > 0 && (
              <div>
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <TrendingUp className="h-3 w-3" />
                  高频问题
                </h4>
                <div className="space-y-1.5">
                  {topQuestions.map((q, index) => (
                    <div
                      key={`${q.text.slice(0, 30)}-${index}`}
                      className="flex gap-2 rounded border border-slate-100 bg-slate-50/50 px-2.5 py-2"
                    >
                      <span className="mt-0.5 shrink-0 font-mono text-[11px] font-semibold text-teal-600">
                        {index + 1}.
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-[13px] leading-relaxed text-slate-800">
                          {q.text}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          {q.category && (
                            <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                              {CATEGORY_LABELS[q.category] ?? q.category}
                            </span>
                          )}
                          {q.frequency > 1 && (
                            <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                              出现 {q.frequency} 次
                            </span>
                          )}
                          {q.avgDifficulty != null && (
                            <span className="text-[10px] text-slate-400">
                              难度 {q.avgDifficulty}
                            </span>
                          )}
                          {q.hasEvidence && (
                            <span className="rounded border border-teal-200 bg-teal-50 px-1.5 py-0.5 text-[10px] text-teal-600">
                              有证据
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 右侧：分类分布 + 来源分布 */}
            <div className="space-y-4">
              {/* 分类分布 — 水平条形图 */}
              {categories.length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    问题分类
                  </h4>
                  <div className="space-y-1.5">
                    {categories.slice(0, 6).map((cat) => (
                      <div key={cat.category} className="flex items-center gap-2">
                        <span className="w-16 shrink-0 truncate text-right text-[11px] text-slate-600">
                          {cat.label}
                        </span>
                        <div className="relative h-5 flex-1 overflow-hidden rounded bg-slate-100">
                          <div
                            className="absolute inset-y-0 left-0 rounded bg-teal-500/70 transition-all duration-500"
                            style={{ width: `${Math.max((cat.count / maxCategoryCount) * 100, 4)}%` }}
                          />
                          <span className="relative z-10 flex h-full items-center px-2 text-[10px] font-semibold tabular-nums text-slate-700">
                            {cat.count}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 来源分布 */}
              {sources.length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    来源分布
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {sources.map((src) => (
                      <span
                        key={src.source}
                        className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600"
                      >
                        {src.label}
                        <span className="font-semibold tabular-nums text-slate-800">{src.count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50/50 px-3 py-2">
      <div className="flex items-center gap-1.5 text-slate-400">
        <Icon className="h-3 w-3" />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <p className="mt-1 text-lg font-bold tabular-nums text-slate-800">{String(value)}</p>
    </div>
  );
}
