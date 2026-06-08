import { Loader2 } from "lucide-react";
import { AppHeader } from "@/components/app-header";

export default function CompanyLoading() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader subtitle="公司面试画像" />
      <div className="flex items-center justify-center py-32">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-cyan-500" />
          <p className="text-sm text-zinc-500">加载公司画像...</p>
        </div>
      </div>
    </div>
  );
}
