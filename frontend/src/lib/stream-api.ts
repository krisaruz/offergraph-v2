/**
 * SSE Stream API — 通过 fetch + ReadableStream 消费流式搜索事件。
 * 参考 Claude Code 子 agent 架构：逐事件分发回调，支持 abort 取消。
 */

import type { ActivityLogEntry, FeedItem, SearchProfile, StreamCallbacks } from "./types";
import { API_BASE } from "./api";

let _logIdCounter = 0;

interface PendingLine {
  resolve: () => void;
}

/**
 * 连接流式搜索 SSE 端点。
 * 返回 abort 函数用于取消连接。
 */
export function connectSearchStream(
  profile: SearchProfile,
  callbacks: StreamCallbacks
): () => void {
  const abortController = new AbortController();

  const STREAM_TIMEOUT_MS = 180000;
  const timeoutId = setTimeout(() => {
    abortController.abort();
    callbacks.onSearchError?.("搜索超时，请稍后重试");
  }, STREAM_TIMEOUT_MS);

  const body = {
    identity: profile.identity,
    directions: profile.directions,
    target_companies: profile.target_companies,
    regions: profile.regions,
    custom_needs: profile.custom_needs ?? "",
  };

  const url = `${API_BASE}/api/feed/search/stream`;

  (async () => {
    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: abortController.signal,
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      callbacks.onSearchError?.((err as Error).message);
      return;
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const errBody = await response.json();
        message = errBody.detail ?? errBody.message ?? message;
      } catch {
        // ignore
      }
      callbacks.onSearchError?.(message);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      callbacks.onSearchError?.("无法读取响应流");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 按 \n\n 切分 SSE 事件
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          if (!part.trim()) continue;
          const parsed = parseSSEEvent(part);
          if (parsed) {
            dispatchEvent(parsed.event, parsed.data, callbacks);
          }
        }
      }

      // 处理剩余缓冲区
      if (buffer.trim()) {
        const parsed = parseSSEEvent(buffer);
        if (parsed) {
          dispatchEvent(parsed.event, parsed.data, callbacks);
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      callbacks.onSearchError?.((err as Error).message);
    } finally {
      clearTimeout(timeoutId);
      reader.releaseLock();
    }
  })();

  return () => {
    clearTimeout(timeoutId);
    abortController.abort();
  };
}

function parseSSEEvent(raw: string): { event: string; data: Record<string, unknown> } | null {
  const lines = raw.split("\n");
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      eventType = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
    } else if (line.startsWith("id: ")) {
      // skip
    }
  }

  if (dataLines.length === 0) return null;

  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event: eventType, data };
  } catch {
    return null;
  }
}

function normalizeStreamItem(raw: Record<string, unknown>): FeedItem {
  return {
    source: String(raw.source ?? ""),
    source_url: String(raw.source_url ?? raw.sourceUrl ?? ""),
    title: (raw.title as string) ?? null,
    snippet: (raw.snippet as string) ?? null,
    published_at: (raw.published_at ?? raw.publishedAt) as string | null,
    final_score: (raw.final_score ?? raw.finalScore) as number | null,
    trust_label: (raw.trust_label ?? raw.trustLabel) as string | null,
    has_full_text: Boolean(raw.has_full_text ?? raw.hasFullText),
    tags: (raw.tags as string[]) ?? [],
    source_document_id: raw.source_document_id as string | undefined,
  };
}

function dispatchEvent(
  eventType: string,
  data: Record<string, unknown>,
  cbs: StreamCallbacks
) {
  switch (eventType) {
    case "session_created":
      cbs.onSessionCreated?.(String(data.session_id ?? ""));
      break;

    case "phase_start":
      cbs.onPhaseStart?.((data.phase as import("./types").AgentPhase) ?? "searching", data);
      break;

    case "phase_completed":
      cbs.onPhaseCompleted?.((data.phase as import("./types").AgentPhase) ?? "searching", data);
      break;

    case "query_plan_ready":
      cbs.onQueryPlanReady?.(data);
      break;

    case "search_started":
      cbs.onSearchStarted?.(String(data.source ?? ""), data);
      break;

    case "source_results": {
      const items = Array.isArray(data.items)
        ? data.items.map((it) => normalizeStreamItem(it as Record<string, unknown>))
        : [];
      cbs.onSourceResults?.(String(data.source ?? ""), items);
      break;
    }

    case "source_completed":
      cbs.onSourceCompleted?.(String(data.source ?? ""), data);
      break;

    case "source_error":
      cbs.onSourceError?.(String(data.source ?? ""), String(data.error ?? ""));
      break;

    case "source_timeout":
      cbs.onSourceTimeout?.(String(data.source ?? ""), Number(data.timeout_s ?? 0));
      break;

    case "ranking_completed":
      cbs.onRankingCompleted?.(data);
      break;

    case "fetch_started":
      cbs.onFetchStarted?.(data);
      break;

    case "fetch_completed":
      cbs.onFetchCompleted?.(data);
      break;

    case "extract_completed":
      cbs.onExtractCompleted?.(data);
      break;

    case "search_completed":
      cbs.onSearchCompleted?.(data);
      break;

    case "search_error":
      cbs.onSearchError?.(String(data.error ?? data.message ?? ""));
      break;

    case "search_blocked":
      cbs.onSearchBlocked?.(String(data.reason ?? ""));
      break;

    case "activity_log": {
      const entry: ActivityLogEntry = {
        id: `log_${++_logIdCounter}`,
        message: String(data.message ?? ""),
        level: (data.level as ActivityLogEntry["level"]) ?? "info",
        timestamp: Date.now(),
      };
      cbs.onActivityLog?.(entry);
      break;
    }

    case "enhance_start":
      cbs.onEnhanceStart?.(data);
      break;

    case "enhance_progress":
      cbs.onEnhanceProgress?.(data);
      break;

    case "enhance_completed":
      cbs.onEnhanceCompleted?.(data);
      break;

    case "llm_start":
      cbs.onLlmStart?.(String(data.doc_id ?? ""), String(data.doc_title ?? ""));
      break;

    case "llm_chunk":
      cbs.onLlmChunk?.(String(data.doc_id ?? ""), String(data.token ?? ""));
      break;

    case "llm_summary":
      cbs.onLlmSummary?.(
        String(data.doc_id ?? ""),
        String(data.summary ?? ""),
        Number(data.question_count ?? 0),
      );
      break;

    case "stream_end":
      cbs.onStreamEnd?.();
      break;
  }
}
