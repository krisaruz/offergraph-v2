import { Crosshair, Database, FileSearch, Signal } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { ProfileForm } from "@/components/profile-form";

const FEATURES = [
  { icon: Database, label: "多源聚合", desc: "牛客、脉脉、小红书、搜索引擎" },
  { icon: FileSearch, label: "结构化抽取", desc: "LLM 自动提取面试问题与证据" },
  { icon: Crosshair, label: "可信评级", desc: "来源可靠性 × 证据覆盖率" },
  { icon: Signal, label: "实时流式", desc: "搜索过程全程可见" },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <AppHeader />

      <main className="relative mx-auto max-w-6xl px-6 py-10">
        <div className="pointer-events-none fixed inset-0 radar-grid opacity-50" />

        <div className="relative grid gap-10 lg:grid-cols-5">
          {/* Left: Form */}
          <div className="lg:col-span-3">
            <div className="mb-6">
              <h2 className="text-xs tracking-widest text-cyan-500/80 uppercase">
                Search Parameters
              </h2>
              <p className="mt-1 text-2xl font-bold tracking-tight text-zinc-100">
                面试情报分析系统
              </p>
              <p className="mt-2 text-sm text-zinc-500">
                配置搜索画像，系统将从多个平台实时聚合面经，AI 结构化提取面试问题。
              </p>
            </div>

            <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-6">
              <ProfileForm />
            </div>
          </div>

          {/* Right: Radar + features */}
          <div className="flex flex-col justify-center lg:col-span-2">
            {/* Radar circles */}
            <div className="relative mx-auto mb-10 h-56 w-56">
              {[56, 84, 112].map((r) => (
                <div
                  key={r}
                  className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-500/10"
                  style={{ width: r * 2, height: r * 2 }}
                />
              ))}
              <div className="absolute left-1/2 top-1/2 h-0.5 w-28 origin-left -translate-y-1/2 bg-gradient-to-r from-cyan-400/60 to-transparent animate-radar-sweep" />
              <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-400 animate-signal-blink" />
              {[
                { x: 30, y: 20 },
                { x: 70, y: 35 },
                { x: 45, y: 75 },
                { x: 80, y: 65 },
                { x: 25, y: 60 },
              ].map((pos, i) => (
                <div
                  key={i}
                  className="absolute h-1.5 w-1.5 rounded-full bg-cyan-400/60 animate-signal-blink"
                  style={{
                    left: `${pos.x}%`,
                    top: `${pos.y}%`,
                    animationDelay: `${i * 0.4}s`,
                  }}
                />
              ))}
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2">
                <span className="text-[10px] text-cyan-500/50">
                  SIGNAL SCANNING
                </span>
              </div>
            </div>

            {/* Feature list */}
            <div className="space-y-3">
              {FEATURES.map((f) => (
                <div
                  key={f.label}
                  className="flex items-center gap-3 rounded-md border border-zinc-800/40 bg-zinc-900/20 px-4 py-2.5 transition hover:border-cyan-500/20"
                >
                  <f.icon className="h-4 w-4 shrink-0 text-cyan-500/60" />
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-zinc-300">
                      {f.label}
                    </span>
                    <span className="ml-2 text-xs text-zinc-600">
                      {f.desc}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
