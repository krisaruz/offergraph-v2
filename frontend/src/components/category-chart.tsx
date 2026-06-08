import { CATEGORY_LABELS } from "@/lib/format";

interface CategoryChartProps {
  distribution: Record<string, number>;
  variant?: "bar" | "pie";
}

const CHART_COLORS = [
  "#10b981",
  "#14b8a6",
  "#06b6d4",
  "#8b5cf6",
  "#f59e0b",
  "#ef4444",
  "#64748b",
];

export function CategoryChart({
  distribution,
  variant = "bar",
}: CategoryChartProps) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (entries.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        暂无分类数据
      </div>
    );
  }

  if (variant === "pie") {
    let cumulative = 0;
    const segments = entries.map(([category, count], index) => {
      const percent = count / total;
      const start = cumulative * 360;
      cumulative += percent;
      const end = cumulative * 360;
      const color = CHART_COLORS[index % CHART_COLORS.length];
      const largeArc = end - start > 180 ? 1 : 0;
      const startRad = ((start - 90) * Math.PI) / 180;
      const endRad = ((end - 90) * Math.PI) / 180;
      const x1 = 50 + 40 * Math.cos(startRad);
      const y1 = 50 + 40 * Math.sin(startRad);
      const x2 = 50 + 40 * Math.cos(endRad);
      const y2 = 50 + 40 * Math.sin(endRad);

      return {
        category,
        count,
        percent,
        color,
        path:
          percent >= 0.999
            ? `M 50 10 A 40 40 0 1 1 49.99 10 Z`
            : `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`,
      };
    });

    return (
      <div className="flex flex-col items-center gap-6 md:flex-row">
        <svg viewBox="0 0 100 100" className="h-40 w-40 shrink-0">
          {segments.map((seg) => (
            <path
              key={seg.category}
              d={seg.path}
              fill={seg.color}
              className="opacity-90 transition hover:opacity-100"
            />
          ))}
          <circle cx="50" cy="50" r="22" fill="#18181b" />
          <text
            x="50"
            y="48"
            textAnchor="middle"
            className="fill-zinc-400 text-[6px]"
          >
            共 {total}
          </text>
          <text
            x="50"
            y="56"
            textAnchor="middle"
            className="fill-zinc-500 text-[5px]"
          >
            条问题
          </text>
        </svg>
        <div className="flex-1 space-y-2">
          {segments.map((seg) => (
            <div
              key={seg.category}
              className="flex items-center justify-between text-sm"
            >
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: seg.color }}
                />
                <span className="text-zinc-300">
                  {CATEGORY_LABELS[seg.category] ?? seg.category}
                </span>
              </div>
              <span className="text-zinc-500">
                {seg.count} ({Math.round(seg.percent * 100)}%)
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const maxCount = Math.max(...entries.map(([, c]) => c));

  return (
    <div className="space-y-3">
      {entries.map(([category, count], index) => {
        const percent = (count / maxCount) * 100;
        const color = CHART_COLORS[index % CHART_COLORS.length];
        return (
          <div key={category}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="text-zinc-300">
                {CATEGORY_LABELS[category] ?? category}
              </span>
              <span className="text-zinc-500">
                {count} ({Math.round((count / total) * 100)}%)
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${percent}%`, backgroundColor: color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
