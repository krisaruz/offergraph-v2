import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-500" />
        <p className="text-sm text-zinc-500">加载中...</p>
      </div>
    </div>
  );
}
