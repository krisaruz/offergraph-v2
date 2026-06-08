import { Shield, ShieldAlert, ShieldCheck } from "lucide-react";

interface TrustBadgeProps {
  label?: string | null;
  size?: "sm" | "md";
}

const CONFIG: Record<string, { text: string; color: string; icon: typeof Shield }> = {
  high: { text: "高可信", color: "bg-emerald-400", icon: ShieldCheck },
  medium: { text: "中等", color: "bg-amber-400", icon: Shield },
  low: { text: "低可信", color: "bg-red-400", icon: ShieldAlert },
};

export function TrustBadge({ label, size = "md" }: TrustBadgeProps) {
  const key = (label ?? "medium").toLowerCase();
  const config = CONFIG[key] ?? CONFIG.medium;
  const Icon = config.icon;
  const isSmall = size === "sm";

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block w-0.5 rounded-full ${config.color} ${isSmall ? "h-3" : "h-4"}`} />
      <Icon className={`text-zinc-500 ${isSmall ? "h-3 w-3" : "h-3.5 w-3.5"}`} aria-hidden="true" />
      <span className={`text-zinc-500 ${isSmall ? "text-[10px]" : "text-xs"}`}>
        {config.text}
      </span>
    </span>
  );
}
