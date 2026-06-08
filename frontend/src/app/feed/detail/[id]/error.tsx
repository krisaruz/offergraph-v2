"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { AppHeader } from "@/components/app-header";

export default function FeedDetailError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);

  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="面经详情" />
      <div className="flex items-center justify-center px-6 py-32">
        <div className="max-w-md text-center">
          <AlertTriangle className="mx-auto mb-4 h-10 w-10 text-red-400" />
          <h2 className="mb-2 text-lg font-semibold text-zinc-100">加载面经详情失败</h2>
          <p className="mb-6 text-sm text-zinc-500">{error.message || "请确认后端服务已启动且该文档 ID 有效"}</p>
          <div className="flex items-center justify-center gap-3">
            <Link href="/feed" className="inline-flex items-center gap-2 rounded-md border border-zinc-800 px-4 py-2 text-sm text-zinc-400 hover:border-zinc-700 hover:text-zinc-300">
              <ArrowLeft className="h-4 w-4" />返回列表
            </Link>
            <button onClick={reset} className="inline-flex items-center gap-2 rounded-md bg-cyan-600 px-4 py-2 text-sm text-white hover:bg-cyan-500">
              <RefreshCw className="h-4 w-4" />重试
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
