"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
} from "lucide-react";
import type { AgentPhase, AgentState } from "@/lib/types";
import { formatDuration } from "@/lib/format";

interface AgentActivityProps {
  agents: AgentState[];
  currentPhase?: AgentPhase | null;
  totalResults?: number;
  searchDurationMs?: number;
}

const PHASE_LABELS: Record<AgentPhase, string> = {
  planning: "规划搜索",
  searching: "多源搜索",
  fetching: "抓取正文",
  extracting: "LLM 抽取",
  ranking: "排序优化",
};

export function AgentActivity({
  agents,
  currentPhase,
  totalResults,
  searchDurationMs,
}: AgentActivityProps) {
  return (
    <div className="rounded-md border border-zinc-800/60 bg-zinc-900/30 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-3.5 w-3.5 text-cyan-500" />
        <h3 className="font-mono text-xs tracking-wider text-zinc-500 uppercase">
          Agent Activity
        </h3>
      </div>

      {currentPhase && (
        <div className="mb-3 rounded border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
          <div className="flex items-center gap-2 font-mono text-[11px] text-cyan-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>{PHASE_LABELS[currentPhase] ?? currentPhase}</span>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="flex items-start gap-2 rounded border border-zinc-800/30 bg-zinc-900/20 px-3 py-2"
          >
            <div className="mt-0.5 shrink-0">
              {agent.status === "running" && (
                <Loader2 className="h-3 w-3 animate-spin text-cyan-400" />
              )}
              {agent.status === "done" && (
                <CheckCircle2 className="h-3 w-3 text-cyan-500" />
              )}
              {agent.status === "error" && (
                <XCircle className="h-3 w-3 text-red-400" />
              )}
              {agent.status === "timeout" && (
                <Clock className="h-3 w-3 text-amber-400" />
              )}
              {agent.status === "blocked" && (
                <AlertTriangle className="h-3 w-3 text-zinc-500" />
              )}
              {agent.status === "idle" && (
                <div className="h-3 w-3 rounded-full border border-zinc-700" />
              )}
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[11px] text-zinc-300">
                  {agent.displayName}
                </span>
                {agent.durationMs != null && agent.durationMs > 0 && (
                  <span className="shrink-0 font-mono text-[10px] text-zinc-600">
                    {formatDuration(agent.durationMs)}
                  </span>
                )}
              </div>

              {agent.query && (
                <p className="mt-0.5 truncate font-mono text-[10px] text-zinc-600">
                  &ldquo;{agent.query}&rdquo;
                </p>
              )}

              {agent.progress && (
                <p className="mt-0.5 font-mono text-[10px] text-zinc-600">
                  {agent.progress}
                </p>
              )}

              {agent.errorMessage && (
                <p className="mt-0.5 truncate font-mono text-[10px] text-red-400">
                  {agent.errorMessage}
                </p>
              )}

              {agent.resultCount != null && agent.status === "done" && (
                <p className="mt-0.5 font-mono text-[10px] text-cyan-500">
                  {agent.resultCount} results
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {totalResults != null && totalResults > 0 && (
        <div className="mt-3 border-t border-zinc-800/40 pt-3">
          <div className="flex items-center justify-between font-mono text-[11px]">
            <span className="text-zinc-600">results</span>
            <span className="text-cyan-400">{totalResults}</span>
          </div>
          {searchDurationMs != null && searchDurationMs > 0 && (
            <div className="mt-1 flex items-center justify-between font-mono text-[11px]">
              <span className="text-zinc-600">duration</span>
              <span className="text-zinc-500">{formatDuration(searchDurationMs)}</span>
            </div>
          )}
        </div>
      )}

      {agents.length === 0 && !currentPhase && (
        <p className="py-6 text-center font-mono text-[10px] text-zinc-700">
          waiting for search...
        </p>
      )}
    </div>
  );
}
