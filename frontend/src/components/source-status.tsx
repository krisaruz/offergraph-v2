import { Globe, MessageSquare, Search } from "lucide-react";
import { SOURCE_LABELS } from "@/lib/format";

interface SourceStatusProps {
  sourcesStatus: Record<string, string>;
}

const SOURCE_ICONS: Record<string, typeof Globe> = {
  nowcoder: MessageSquare,
  maimai: MessageSquare,
  xiaohongshu: Globe,
  search_engine: Search,
  web: Globe,
};

function getStatusDot(status: string): string {
  if (status === "ok") return "bg-emerald-400";
  if (status === "timeout") return "bg-amber-400";
  return "bg-red-400";
}

export function SourceStatus({ sourcesStatus }: SourceStatusProps) {
  const entries = Object.entries(sourcesStatus);

  if (entries.length === 0) {
    return <div className="text-xs text-zinc-600">等待数据源...</div>;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {entries.map(([source, status]) => {
        const SourceIcon = SOURCE_ICONS[source] ?? Globe;
        return (
          <div key={source} className="inline-flex items-center gap-1.5 text-xs text-zinc-500">
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${getStatusDot(status)}`} />
            <SourceIcon className="h-3 w-3" aria-hidden="true" />
            <span>{SOURCE_LABELS[source] ?? source}</span>
          </div>
        );
      })}
    </div>
  );
}
