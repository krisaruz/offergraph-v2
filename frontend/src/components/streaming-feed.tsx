"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ActivityLogEntry, FeedItem, FeedSearchResponse } from "@/lib/types";
import { connectSearchStream } from "@/lib/stream-api";
import type { SearchProfile } from "@/lib/types";
import { FeedCard } from "./feed-card";
import { ActivityLog, type LlmStreamState } from "./activity-log";
import { SourceStatus } from "./source-status";
import { formatDuration } from "@/lib/format";
import { getCachedFeed } from "@/lib/api";
import { saveSearchResult } from "@/lib/session-storage";
import { AlertCircle, Clock, FileSearch } from "lucide-react";

interface StreamingFeedProps {
  profile: SearchProfile;
  defaultCompany: string;
  defaultPosition: string;
}

export function StreamingFeed({ profile, defaultCompany, defaultPosition }: StreamingFeedProps) {
  const [searching, setSearching] = useState(true);
  const [enhancing, setEnhancing] = useState(false);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [sourcesStatus, setSourcesStatus] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [searchDurationMs, setSearchDurationMs] = useState(0);
  const [fetchedCount, setFetchedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [blockedReason, setBlockedReason] = useState<string | null>(null);
  const [fallbackShown, setFallbackShown] = useState(false);
  const [activityLogs, setActivityLogs] = useState<ActivityLogEntry[]>([]);
  const [llmStreams, setLlmStreams] = useState<LlmStreamState[]>([]);

  const itemsMapRef = useRef<Map<string, FeedItem>>(new Map());
  const llmStreamsRef = useRef<Map<string, LlmStreamState>>(new Map());

  const addLog = useCallback((entry: ActivityLogEntry) => {
    setActivityLogs((prev) => [...prev, entry]);
  }, []);

  const startSearch = useCallback(() => {
    setSearching(true);
    setEnhancing(false);
    setError(null);
    setBlockedReason(null);
    setFallbackShown(false);
    setItems([]);
    setTotal(0);
    setSearchDurationMs(0);
    setFetchedCount(0);
    itemsMapRef.current.clear();
    llmStreamsRef.current.clear();
    setSourcesStatus({});
    setActivityLogs([]);
    setLlmStreams([]);

    let _localLogId = 0;
    const localLog = (message: string, level: ActivityLogEntry["level"] = "info", durationMs?: number) => {
      addLog({ id: `local_${++_localLogId}`, message, level, timestamp: Date.now(), durationMs });
    };

    const SOURCE_NAMES: Record<string, string> = {
      nowcoder: "牛客", maimai: "脉脉", xiaohongshu: "小红书", search_engine: "搜索引擎",
    };

    localLog("正在分析画像，规划搜索策略...");

    const abort = connectSearchStream(profile, {
      onActivityLog(entry) { addLog(entry); },

      onPhaseStart(phase, data) {
        const message = data.message as string;
        if (message) localLog(message);
      },

      onQueryPlanReady(data) {
        const sources = (data.active_sources as string[]) ?? [];
        const queries = (data.queries as Array<{ query: string }>) ?? [];
        const query = queries[0]?.query ?? "";
        for (const src of sources) {
          localLog(`在${SOURCE_NAMES[src] ?? src}搜索「${query}」...`);
        }
      },

      onSearchStarted(source, data) {
        const displayName = (data.display_name as string) ?? SOURCE_NAMES[source] ?? source;
        const queries = (data.queries as string[]) ?? [];
        localLog(`→ ${displayName} 开始搜索（${queries.length} 条查询）`);
      },

      onSourceResults(_source, newItems) {
        for (const item of newItems) {
          const key = item.source_url || `${item.source}_${Math.random()}`;
          if (!itemsMapRef.current.has(key)) {
            itemsMapRef.current.set(key, item);
          }
        }
        setItems(Array.from(itemsMapRef.current.values()));
      },

      onSourceCompleted(source, data) {
        const durationMs = (data.duration_ms as number) ?? 0;
        const count = (data.count as number) ?? 0;
        setSourcesStatus((prev) => ({ ...prev, [source]: "ok" }));
        localLog(`✓ ${SOURCE_NAMES[source] ?? source} 完成：${count} 条结果`, "success", durationMs);
      },

      onSourceError(source, errorMsg) {
        setSourcesStatus((prev) => ({ ...prev, [source]: `error:${errorMsg.slice(0, 30)}` }));
        localLog(`✗ ${SOURCE_NAMES[source] ?? source} 失败：${errorMsg.slice(0, 40)}`, "error");
      },

      onSourceTimeout(source) {
        setSourcesStatus((prev) => ({ ...prev, [source]: "timeout" }));
        localLog(`✗ ${SOURCE_NAMES[source] ?? source} 超时`, "warning");
      },

      onRankingCompleted(data) {
        const totalItems = (data.total as number) ?? itemsMapRef.current.size;
        setTotal(totalItems);
        localLog(`排序完成：${totalItems} 条面经`, "success");
        const finalItems = (data.final_items as FeedItem[]) ?? [];
        if (finalItems.length > 0) {
          const newMap = new Map<string, FeedItem>();
          for (const item of finalItems) {
            const key = item.source_url || `${item.source}_${Math.random()}`;
            newMap.set(key, item);
          }
          itemsMapRef.current = newMap;
          setItems(Array.from(newMap.values()));
        }
      },

      onSearchCompleted(data) {
        const finalTotal = (data.total as number) ?? itemsMapRef.current.size;
        const durationMs = (data.search_duration_ms as number) ?? 0;
        const finalSourcesStatus = (data.sources_status as Record<string, string>) ?? {};
        setSearching(false);
        setTotal(finalTotal);
        setSearchDurationMs(durationMs);
        setSourcesStatus(finalSourcesStatus);
        localLog(`搜索完成！${(durationMs / 1000).toFixed(1)} 秒，${finalTotal} 条结果`, "success");
      },

      onEnhanceStart() {
        setEnhancing(true);
      },

      onFetchStarted(data) {
        const index = data.index as number;
        const total = data.total as number;
        const url = (data.source_url as string) ?? "";
        localLog(`抓取 [${index}/${total}] ${url.slice(0, 60)}...`);
      },

      onFetchCompleted(data) {
        const sourceUrl = data.source_url as string;
        const hasFullText = data.has_full_text as boolean;
        if (sourceUrl) {
          for (const [key, item] of itemsMapRef.current) {
            if (item.source_url === sourceUrl) {
              itemsMapRef.current.set(key, {
                ...item,
                has_full_text: hasFullText,
                source_document_id: data.source_document_id as string | undefined,
              });
              break;
            }
          }
          setItems(Array.from(itemsMapRef.current.values()));
        }
        setFetchedCount((prev) => prev + 1);
        if (hasFullText) {
          localLog(`✓ 抓取成功：${sourceUrl.slice(0, 50)}...`, "success");
        }
      },

      onExtractCompleted(data) {
        const docId = data.source_document_id as string;
        const questionCount = (data.question_count as number) ?? 0;
        const evidenceCov = (data.evidence_coverage as number) ?? undefined;
        const tags = (data.tags as string[]) ?? [];
        if (docId) {
          for (const [key, item] of itemsMapRef.current) {
            if (item.source_document_id === docId) {
              itemsMapRef.current.set(key, {
                ...item,
                question_count: questionCount,
                evidence_coverage: evidenceCov,
                tags: item.tags?.length ? item.tags : tags,
              });
              break;
            }
          }
          setItems(Array.from(itemsMapRef.current.values()));
        }
        if (questionCount > 0) {
          localLog(`✓ 提取完成：${questionCount} 道面试题`, "success");
        }
      },

      onEnhanceCompleted(data) {
        setEnhancing(false);
        setFetchedCount((data.fetched_count as number) ?? fetchedCount);
        localLog("深度分析完成", "success");
        const response: FeedSearchResponse = {
          sessionId: "", status: "success",
          items: Array.from(itemsMapRef.current.values()),
          total: itemsMapRef.current.size,
          sourcesStatus: {}, cachedCount: 0,
          freshCount: itemsMapRef.current.size,
          searchDuration: searchDurationMs,
          qualityReport: null, error: null,
        };
        try { saveSearchResult(response); } catch {}
      },

      onLlmStart(docId, docTitle) {
        llmStreamsRef.current.set(docId, { docId, docTitle, content: "", streaming: true });
        setLlmStreams(Array.from(llmStreamsRef.current.values()));
      },

      onLlmChunk(docId, token) {
        const existing = llmStreamsRef.current.get(docId);
        if (existing) {
          existing.content += token;
          llmStreamsRef.current.set(docId, { ...existing });
          setLlmStreams(Array.from(llmStreamsRef.current.values()));
        }
      },

      onLlmSummary(docId, summary, questionCount) {
        const existing = llmStreamsRef.current.get(docId);
        if (existing) {
          llmStreamsRef.current.set(docId, { ...existing, streaming: false, summary, questionCount });
          setLlmStreams(Array.from(llmStreamsRef.current.values()));
        }
      },

      onStreamEnd() { setSearching(false); setEnhancing(false); },
      onSearchError(errMsg) { setSearching(false); setEnhancing(false); setError(errMsg); },
      onSearchBlocked(reason) { setSearching(false); setBlockedReason(reason); },
    });

    return abort;
  }, [profile, addLog, fetchedCount, searchDurationMs]);

  useEffect(() => {
    const abortFn = startSearch();
    return () => abortFn?.();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <ActivityLog
        entries={activityLogs}
        searchCompleted={!searching}
        searchDurationMs={searchDurationMs}
        totalResults={total}
        enhancing={enhancing}
        llmStreams={llmStreams}
      />

      {/* Stats bar */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border border-zinc-800/40 bg-zinc-900/30 px-4 py-2.5">
        <SourceStatus sourcesStatus={sourcesStatus} />
        <div className="ml-auto flex items-center gap-4 text-xs text-zinc-500">
          <div className="flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            {searching ? (
              <span className="text-cyan-400">搜索中...</span>
            ) : searchDurationMs > 0 ? (
              formatDuration(searchDurationMs)
            ) : "—"}
          </div>
          <div className="flex items-center gap-1.5">
            <FileSearch className="h-3 w-3" />
            {total > 0 ? total : items.length || "..."} 条结果
          </div>
          {fetchedCount > 0 && (
            <span className="text-zinc-600">{fetchedCount} 篇已抓取</span>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0 flex-1">{error}</span>
          {!fallbackShown && (
            <button
              onClick={async () => {
                setFallbackShown(true);
                try {
                  const cached = await getCachedFeed(profile.target_companies[0]);
                  if (cached.items.length > 0) {
                    saveSearchResult(cached);
                    setItems(cached.items);
                    setTotal(cached.total);
                    setSourcesStatus(cached.sourcesStatus);
                    setError(null);
                  }
                } catch {}
              }}
              className="shrink-0 rounded border border-zinc-700 px-2 py-1 text-[10px] text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
            >
              加载缓存
            </button>
          )}
        </div>
      )}

      {blockedReason && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-amber-400">
          搜索被阻断：{blockedReason}
        </div>
      )}

      {/* Results */}
      {items.length === 0 && !searching && !error ? (
        <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-zinc-800 px-6 py-16 text-center">
          <div className="relative mb-4 h-16 w-16">
            {[16, 28, 40].map((r) => (
              <div key={r} className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-zinc-800" style={{ width: r * 2, height: r * 2 }} />
            ))}
            <div className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-zinc-700" />
          </div>
          <h3 className="mb-1 text-sm text-zinc-400">未找到匹配结果</h3>
          <p className="max-w-sm text-xs text-zinc-600">请尝试调整目标公司或岗位方向后重新搜索</p>
        </div>
      ) : items.length === 0 && searching ? (
        <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-zinc-800 px-6 py-16 text-center">
          <div className="relative mb-4 h-16 w-16">
            {[16, 28, 40].map((r) => (
              <div key={r} className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-500/10 animate-radar-pulse" style={{ width: r * 2, height: r * 2, animationDelay: `${r * 20}ms` }} />
            ))}
            <div className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-400 animate-signal-blink" />
          </div>
          <h3 className="mb-1 text-sm text-zinc-300">正在搜索...</h3>
          <p className="text-xs text-zinc-600">从多个数据源获取面经，结果将实时展示</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div
              key={item.source_url || index}
              className="animate-fade-in"
              style={{ animationFillMode: "backwards", animationDelay: `${Math.min(index * 30, 200)}ms` }}
            >
              <FeedCard item={item} defaultCompany={defaultCompany} defaultPosition={defaultPosition} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
