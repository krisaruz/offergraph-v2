import type { Identity } from "./types";

export const IDENTITY_LABELS: Record<Identity, string> = {
  working_switch: "在职跳槽",
  fresh_grad: "应届生",
  intern: "实习生",
};

export const SOURCE_LABELS: Record<string, string> = {
  nowcoder: "牛客",
  maimai: "脉脉",
  xiaohongshu: "小红书",
  search_engine: "搜索引擎",
  web: "网页",
  zhihu: "知乎",
};

export const CATEGORY_LABELS: Record<string, string> = {
  fundamentals: "基础知识",
  system_design: "系统设计",
  algorithm: "算法",
  project_deep_dive: "项目深挖",
  behavioral: "行为面试",
  other: "其他",
};

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "未知日期";
  try {
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) return dateStr;
    return date.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} 毫秒`;
  const seconds = (ms / 1000).toFixed(1);
  return `${seconds} 秒`;
}

export function formatScore(score?: number | null): string {
  if (score == null) return "—";
  return `${Math.round(score * 100)}%`;
}

export function formatPercent(value?: number | null): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}
