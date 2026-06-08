"use client";

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2, AlertTriangle, Loader2, XCircle,
  ChevronDown, ChevronRight, Bot, Terminal,
} from "lucide-react";
import type { ActivityLogEntry } from "@/lib/types";
import { formatDuration } from "@/lib/format";

export interface LlmStreamState {
  docId: string;
  docTitle: string;
  content: string;
  streaming: boolean;
  summary?: string;
  questionCount?: number;
}

interface ActivityLogProps {
  entries: ActivityLogEntry[];
  searchCompleted: boolean;
  searchDurationMs: number;
  totalResults: number;
  enhancing: boolean;
  llmStreams: LlmStreamState[];
}

export function ActivityLog({
  entries, searchCompleted, searchDurationMs, totalResults, enhancing, llmStreams,
}: ActivityLogProps) {
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current && !collapsed) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length, collapsed, llmStreams]);

  useEffect(() => {
    if (searchCompleted && !enhancing && llmStreams.every((s) => !s.streaming)) {
      const timer = setTimeout(() => setCollapsed(true), 2000);
      return () => clearTimeout(timer);
    }
  }, [searchCompleted, enhancing, llmStreams]);

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="mb-4 flex w-full items-center gap-2 rounded-md border border-zinc-800/60 bg-zinc-900/40 px-3 py-2 text-left transition hover:border-zinc-700"
      >
        <ChevronRight className="h-3 w-3 text-zinc-600" />
        <CheckCircle2 className="h-3 w-3 text-cyan-500" />
        <span className="text-xs text-zinc-400">
          {formatDuration(searchDurationMs)} 内找到 {totalResults} 条面经
        </span>
        {enhancing && (
          <span className="ml-auto flex items-center gap-1 text-xs text-zinc-600">
            <Loader2 className="h-3 w-3 animate-spin text-cyan-500" />
            深度分析中...
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="mb-4 overflow-hidden rounded-md border border-zinc-800/60 bg-zinc-950">
      {/* Header */}
      <button
        onClick={() => searchCompleted && !enhancing && setCollapsed(true)}
        className="flex w-full items-center gap-2 border-b border-zinc-800/40 bg-zinc-900/40 px-3 py-2 text-left transition hover:bg-zinc-900/60"
      >
        {searchCompleted && !enhancing ? (
          <ChevronDown className="h-3 w-3 text-zinc-600" />
        ) : (
          <Loader2 className="h-3 w-3 animate-spin text-cyan-500" />
        )}
        <Terminal className="h-3 w-3 text-zinc-600" />
        <span className="text-xs text-zinc-500">
          {!searchCompleted ? "搜索进行中..." : enhancing ? "深度分析中..." : "搜索日志"}
        </span>
        {enhancing && (
          <span className="ml-auto flex items-center gap-1 text-xs text-cyan-500/60">
            <Loader2 className="h-3 w-3 animate-spin" />
            LLM 分析
          </span>
        )}
      </button>

      {/* Log entries */}
      <div ref={scrollRef} className="max-h-64 overflow-y-auto px-3 py-2">
        <div className="space-y-0.5">
          {entries.map((entry, index) => (
            <LogEntry
              key={entry.id}
              entry={entry}
              isLast={index === entries.length - 1 && llmStreams.length === 0}
              isAfterSearch={searchCompleted && index > entries.findIndex((e) => e.level === "success")}
            />
          ))}

          {llmStreams.map((stream) => (
            <LlmStreamBlock key={stream.docId} stream={stream} />
          ))}

          {!searchCompleted && llmStreams.length === 0 && (
            <div className="flex items-center gap-2 py-0.5">
              <span className="font-mono text-xs text-zinc-600">❯</span>
              <span className="inline-block h-3 w-0.5 bg-cyan-400 animate-cursor" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LlmStreamBlock({ stream }: { stream: LlmStreamState }) {
  const contentRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [stream.content]);

  if (!stream.streaming && stream.summary) {
    return (
      <div className="my-1 animate-fade-in rounded border border-zinc-800/40 bg-zinc-900/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-3 w-3 shrink-0 text-cyan-500" />
          <span className="text-xs text-zinc-400">{stream.docTitle}</span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">{stream.summary}</p>
      </div>
    );
  }

  return (
    <div className="my-1 animate-fade-in rounded border border-zinc-800/40 bg-zinc-900/20">
      <div className="flex items-center gap-2 border-b border-zinc-800/30 px-3 py-1.5">
        <Bot className="h-3 w-3 text-cyan-500/60" />
        <span className="text-xs text-zinc-500">{stream.docTitle}</span>
        {stream.streaming && (
          <span className="ml-auto flex items-center gap-1">
            <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-cyan-400" />
            <span className="text-[10px] text-cyan-500/60">生成中</span>
          </span>
        )}
      </div>
      <pre
        ref={contentRef}
        className="max-h-28 overflow-y-auto whitespace-pre-wrap break-all px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-500"
      >
        {stream.content || <span className="text-zinc-700">等待响应...</span>}
        {stream.streaming && <span className="inline-block h-3 w-0.5 bg-cyan-400 animate-cursor" />}
      </pre>
    </div>
  );
}

function LogEntry({ entry, isLast, isAfterSearch }: {
  entry: ActivityLogEntry;
  isLast: boolean;
  isAfterSearch: boolean;
}) {
  const icon = getIcon(entry.level, isLast && entry.level === "info");
  const textColor = isAfterSearch
    ? "text-zinc-600"
    : entry.level === "success"
      ? "text-cyan-400"
      : entry.level === "warning"
        ? "text-amber-400"
        : entry.level === "error"
          ? "text-red-400"
          : "text-zinc-400";

  return (
    <div className="flex items-start gap-2 py-0.5 animate-fade-in" style={{ animationFillMode: "backwards" }}>
      <div className="mt-0.5 shrink-0">{icon}</div>
      <span className={`text-xs leading-relaxed ${textColor}`}>{entry.message}</span>
      {entry.durationMs != null && entry.durationMs > 0 && (
        <span className="ml-auto shrink-0 text-[10px] tabular-nums text-zinc-700">
          {formatDuration(entry.durationMs)}
        </span>
      )}
    </div>
  );
}

function getIcon(level: ActivityLogEntry["level"], isActive: boolean) {
  if (isActive) return <Loader2 className="h-3 w-3 animate-spin text-cyan-400" />;
  switch (level) {
    case "success": return <CheckCircle2 className="h-3 w-3 text-cyan-500" />;
    case "warning": return <AlertTriangle className="h-3 w-3 text-amber-400" />;
    case "error": return <XCircle className="h-3 w-3 text-red-400" />;
    default: return <span className="text-[10px] text-zinc-700">›</span>;
  }
}
