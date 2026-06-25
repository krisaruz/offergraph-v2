"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import {
  getMaimaiAuthStatus,
  importMaimaiCookie,
  getXhsAuthStatus,
  importXhsCookie,
  toApiError,
  validateAllSources,
} from "@/lib/api";
import type { MaimaiAuthStatus, XhsAuthStatus } from "@/lib/types";

type SourceTab = "maimai" | "xiaohongshu";
type AuthStatus = MaimaiAuthStatus | XhsAuthStatus | null;

function needsLogin(status: AuthStatus): boolean {
  return Boolean(status?.needsLogin || status?.runtimeStatus === "unauthorized" || status?.runtimeStatus === "auth_required");
}

function maimaiStatusText(status: MaimaiAuthStatus | null): string {
  if (!status) return "读取中";
  if (!status.enabled) return "未启用";
  if (needsLogin(status)) return status.runtimeReason ? `已过期：${status.runtimeReason}` : "已过期，请重新授权";
  if (status.hasCookieState) return "已保存";
  if (status.hasConfiguredCookie) return "环境变量已配置";
  return "待授权";
}

function xhsStatusText(status: XhsAuthStatus | null): string {
  if (!status) return "读取中";
  if (!status.enabled) return "未启用";
  if (needsLogin(status)) return status.runtimeReason ? `已过期：${status.runtimeReason}` : "已过期，请重新授权";
  if (status.hasCookieState) return "已保存";
  if (status.hasConfiguredCookie) return "环境变量已配置";
  return "待授权";
}

function formatLastValidated(lastValidatedAt: number | null | undefined): string {
  if (!lastValidatedAt) return "从未验证";
  const now = Date.now();
  // backend returns unix seconds
  const tsMs = lastValidatedAt * 1000;
  const diffMs = now - tsMs;
  if (diffMs < 0) return "刚刚";
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay} 天前`;
  try {
    return new Date(tsMs).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "未知";
  }
}

function shouldRevalidate(
  status: AuthStatus,
  now: number
): boolean {
  if (!status) return false;
  // Only revalidate sources that have some form of saved cookie state.
  if (!status.hasCookieState && !status.hasConfiguredCookie) return false;
  if (needsLogin(status)) return false;
  const intervalHours = status.revalidateIntervalHours ?? 24;
  const intervalMs = intervalHours * 3600 * 1000;
  const lastMs = status.lastValidatedAt ? status.lastValidatedAt * 1000 : 0;
  if (lastMs === 0) return true;
  return now - lastMs >= intervalMs;
}

export function SourceAuthPanel() {
  const [activeTab, setActiveTab] = useState<SourceTab>("maimai");
  const [maimaiStatus, setMaimaiStatus] = useState<MaimaiAuthStatus | null>(null);
  const [xhsStatus, setXhsStatus] = useState<XhsAuthStatus | null>(null);
  const [cookie, setCookie] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [revalidating, setRevalidating] = useState(false);
  const revalidationInFlight = useRef(false);

  const refreshMaimaiStatus = async () => {
    try {
      const nextStatus = await getMaimaiAuthStatus();
      setMaimaiStatus(nextStatus);
      setError(null);
    } catch (err) {
      setError(toApiError(err).message);
    }
  };

  const refreshXhsStatus = async () => {
    try {
      const nextStatus = await getXhsAuthStatus();
      setXhsStatus(nextStatus);
      setError(null);
    } catch (err) {
      setError(toApiError(err).message);
    }
  };

  // 用 ref 持有最新状态，避免 15s 定时器随状态变化重建（否则每次刷新都会重置计时）
  const maimaiStatusRef = useRef<MaimaiAuthStatus | null>(null);
  const xhsStatusRef = useRef<XhsAuthStatus | null>(null);
  maimaiStatusRef.current = maimaiStatus;
  xhsStatusRef.current = xhsStatus;

  useEffect(() => {
    void refreshMaimaiStatus();
    void refreshXhsStatus();
    const timer = window.setInterval(() => {
      void refreshMaimaiStatus();
      void refreshXhsStatus();
      // 使用 ref 中的最新状态判断是否需要自动复验
      const now = Date.now();
      const sourcesToValidate: string[] = [];
      if (shouldRevalidate(maimaiStatusRef.current, now)) sourcesToValidate.push("maimai");
      if (shouldRevalidate(xhsStatusRef.current, now)) sourcesToValidate.push("xiaohongshu");
      if (sourcesToValidate.length > 0 && !revalidationInFlight.current) {
        revalidationInFlight.current = true;
        setRevalidating(true);
        validateAllSources(sourcesToValidate)
          .then(() => Promise.all([refreshMaimaiStatus(), refreshXhsStatus()]))
          .catch((err) => setError(toApiError(err).message))
          .finally(() => {
            revalidationInFlight.current = false;
            setRevalidating(false);
          });
      }
    }, 15000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = cookie.trim();
    if (!value) {
      setError("请粘贴从网页复制的 Cookie");
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      if (activeTab === "maimai") {
        const result = await importMaimaiCookie(value, true);
        setCookie("");
        if (result.saved) {
          setMessage(
            result.validationStatus === "ok"
              ? "脉脉 Cookie 已校验并保存"
              : `已保存，校验状态：${result.validationStatus}`
          );
        } else {
          setError(result.reason || "Cookie 未通过脉脉校验，请重新获取");
        }
        await refreshMaimaiStatus();
      } else {
        const result = await importXhsCookie(value, true);
        setCookie("");
        if (result.saved) {
          setMessage(
            result.validationStatus === "ok"
              ? "小红书 Cookie 已校验并保存"
              : `已保存，校验状态：${result.validationStatus}`
          );
        } else {
          setError(result.reason || "Cookie 未通过小红书校验，请重新获取");
        }
        await refreshXhsStatus();
      }
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  const handleManualValidateAll = async () => {
    setIsValidating(true);
    setError(null);
    try {
      await validateAllSources(["maimai", "xiaohongshu"]);
      await Promise.all([refreshMaimaiStatus(), refreshXhsStatus()]);
      setMessage("已对全部数据源触发复验");
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setIsValidating(false);
    }
  };

  const isMaimaiReady = Boolean(maimaiStatus?.hasCookieState && !needsLogin(maimaiStatus));
  const isXhsReady = Boolean(xhsStatus?.hasCookieState && !needsLogin(xhsStatus));
  const currentReady = activeTab === "maimai" ? isMaimaiReady : isXhsReady;
  const currentStatusText = activeTab === "maimai"
    ? maimaiStatusText(maimaiStatus)
    : xhsStatusText(xhsStatus);
  const currentPlaceholder = activeTab === "maimai"
    ? "粘贴脉脉 Cookie header"
    : "粘贴小红书 Cookie header";
  const currentLastValidated = activeTab === "maimai"
    ? maimaiStatus?.lastValidatedAt
    : xhsStatus?.lastValidatedAt;

  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal-50 text-teal-700">
            <KeyRound className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-900">数据源授权</h3>
            <p className="text-xs text-slate-500">
              {activeTab === "maimai" ? "脉脉" : "小红书"}：{currentStatusText}
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400">
              上次验证：{revalidating ? "正在自动复验..." : formatLastValidated(currentLastValidated)}
            </p>
          </div>
        </div>
        {currentReady ? (
          <CheckCircle2 className="mt-1 h-4 w-4 text-emerald-600" />
        ) : (
          <AlertTriangle className="mt-1 h-4 w-4 text-amber-600" />
        )}
      </div>

      {/* Tab switcher */}
      <div className="mb-3 flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
        <button
          type="button"
          onClick={() => {
            setActiveTab("maimai");
            setMessage(null);
            setError(null);
          }}
          className={`flex-1 rounded px-2 py-1 text-xs font-medium transition ${
            activeTab === "maimai"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          脉脉
          {isMaimaiReady && (
            <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
          )}
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("xiaohongshu");
            setMessage(null);
            setError(null);
          }}
          className={`flex-1 rounded px-2 py-1 text-xs font-medium transition ${
            activeTab === "xiaohongshu"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          小红书
          {isXhsReady && (
            <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
          )}
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">
        <textarea
          value={cookie}
          onChange={(event) => setCookie(event.target.value)}
          rows={3}
          placeholder={currentPlaceholder}
          className="w-full resize-none rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:bg-white"
        />
        <button
          type="submit"
          disabled={saving}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          校验并保存
        </button>
      </form>

      <button
        type="button"
        onClick={handleManualValidateAll}
        disabled={isValidating}
        className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isValidating ? <Loader2 className="h-3 w-3 animate-spin" /> : <ShieldCheck className="h-3 w-3" />}
        {isValidating ? "正在复验全部数据源..." : "立即复验全部数据源"}
      </button>

      {message && (
        <p className="mt-2 rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-xs text-emerald-700">
          {message}
        </p>
      )}
      {error && (
        <p className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700">
          {error}
        </p>
      )}
    </section>
  );
}
