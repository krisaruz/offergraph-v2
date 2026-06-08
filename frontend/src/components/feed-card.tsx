"use client";

import Link from "next/link";
import {
  Building2, Calendar, ExternalLink, FileText, Globe,
  MessageSquare, Search, Briefcase,
} from "lucide-react";
import type { FeedItem } from "@/lib/types";
import { formatDate, formatScore, SOURCE_LABELS } from "@/lib/format";
import { getFeedItemId } from "@/lib/session-storage";
import { TrustBadge } from "./trust-badge";

interface FeedCardProps {
  item: FeedItem;
  defaultCompany?: string;
  defaultPosition?: string;
}

const SOURCE_ICONS: Record<string, typeof Globe> = {
  nowcoder: MessageSquare,
  maimai: MessageSquare,
  xiaohongshu: Globe,
  search_engine: Search,
  web: Globe,
};

export function FeedCard({ item, defaultCompany, defaultPosition }: FeedCardProps) {
  const itemId = getFeedItemId(item);
  const SourceIcon = SOURCE_ICONS[item.source] ?? Globe;
  const company = item.company ?? defaultCompany;
  const position = item.position ?? defaultPosition;
  const score = item.final_score ?? item.relevance_score;

  const trustColor =
    item.trust_label === "high"
      ? "bg-emerald-400"
      : item.trust_label === "low"
        ? "bg-red-400"
        : "bg-amber-400";

  const cardContent = (
    <div className="flex gap-3">
      <div className={`w-0.5 shrink-0 rounded-full ${trustColor}`} />
      <div className="min-w-0 flex-1">
        <h3 className="line-clamp-1 text-sm font-medium text-zinc-200 group-hover:text-cyan-300">
          {item.title ?? "未命名面经"}
        </h3>

        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-600">
          <span className="inline-flex items-center gap-1">
            <SourceIcon className="h-3 w-3" aria-hidden="true" />
            {SOURCE_LABELS[item.source] ?? item.source}
          </span>
          {company && (
            <span className="inline-flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {company}
            </span>
          )}
          {position && (
            <span className="inline-flex items-center gap-1">
              <Briefcase className="h-3 w-3" />
              {position}
            </span>
          )}
          {item.published_at && (
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDate(item.published_at)}
            </span>
          )}
        </div>

        {item.snippet && (
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-500">
            {item.snippet}
          </p>
        )}

        <div className="mt-2 flex items-center gap-3">
          {score != null && (
            <span className="text-xs text-zinc-600">
              匹配 <span className="text-cyan-500">{formatScore(score)}</span>
            </span>
          )}
          {item.has_full_text && (
            <span className="inline-flex items-center gap-1 text-xs text-zinc-600">
              <FileText className="h-3 w-3" />全文
            </span>
          )}
          {item.question_count != null && item.question_count > 0 && (
            <span className="inline-flex items-center gap-1 text-xs text-zinc-600">
              <MessageSquare className="h-3 w-3" />{item.question_count}题
            </span>
          )}
          {item.fetch_policy && item.fetch_policy !== "public_fetch_allowed" && (
            <span className="text-[10px] text-zinc-700">
              {item.fetch_policy === "login_required" ? "需登录" : item.fetch_policy === "robots_disallowed" ? "robots禁止" : item.fetch_policy}
            </span>
          )}
          {!itemId && item.source_url && (
            <ExternalLink className="ml-auto h-3 w-3 text-zinc-700" />
          )}
        </div>
      </div>
    </div>
  );

  const className =
    "group block rounded-md border border-zinc-800/60 bg-zinc-900/30 px-4 py-3 transition hover:border-cyan-500/20 hover:bg-zinc-900/50";

  if (itemId) return <Link href={`/feed/detail/${itemId}`} className={className}>{cardContent}</Link>;
  if (item.source_url) return <a href={item.source_url} target="_blank" rel="noopener noreferrer" className={className}>{cardContent}</a>;
  return <article className={className}>{cardContent}</article>;
}
