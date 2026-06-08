"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { IDENTITY_LABELS } from "@/lib/format";
import { saveProfile } from "@/lib/session-storage";
import type { Identity, SearchProfile } from "@/lib/types";
import { MultiTagInput } from "./multi-tag-input";

const IDENTITIES: Identity[] = ["working_switch", "fresh_grad", "intern"];

const COMPANY_SUGGESTIONS = [
  "字节跳动", "阿里巴巴", "腾讯", "美团", "百度", "华为",
];

const DIRECTION_SUGGESTIONS = [
  "后端开发", "前端开发", "算法工程师", "产品经理", "数据分析",
];

const REGION_SUGGESTIONS = ["北京", "上海", "深圳", "杭州", "广州"];

export function ProfileForm() {
  const router = useRouter();
  const [identity, setIdentity] = useState<Identity>("working_switch");
  const [targetCompanies, setTargetCompanies] = useState<string[]>([]);
  const [directions, setDirections] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [customNeeds, setCustomNeeds] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const profile: SearchProfile = {
      identity,
      directions,
      target_companies: targetCompanies,
      regions,
      custom_needs: customNeeds.trim() || undefined,
    };
    saveProfile(profile);
    router.push("/feed");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-2">
        <label className="block text-sm text-zinc-400">身份类型</label>
        <div className="grid grid-cols-3 gap-2">
          {IDENTITIES.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setIdentity(id)}
              className={`rounded-md border px-3 py-2.5 text-sm font-medium transition ${
                identity === id
                  ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                  : "border-zinc-800 bg-zinc-900/40 text-zinc-500 hover:border-zinc-700 hover:text-zinc-400"
              }`}
            >
              {IDENTITY_LABELS[id]}
            </button>
          ))}
        </div>
      </div>

      <MultiTagInput
        label="目标公司"
        placeholder="输入公司名称，回车添加（可选，留空搜索全部）"
        tags={targetCompanies}
        onChange={setTargetCompanies}
        suggestions={COMPANY_SUGGESTIONS}
      />

      <MultiTagInput
        label="方向 / 岗位"
        placeholder="如：后端开发、算法工程师（可选，留空搜索全部）"
        tags={directions}
        onChange={setDirections}
        suggestions={DIRECTION_SUGGESTIONS}
      />

      <MultiTagInput
        label="目标地区"
        placeholder="如：北京、上海（可选，留空不限地区）"
        tags={regions}
        onChange={setRegions}
        suggestions={REGION_SUGGESTIONS}
      />

      <div className="space-y-2">
        <label htmlFor="customNeeds" className="block text-sm text-zinc-400">
          个性化需求
          <span className="ml-1 text-xs text-zinc-600">（可选）</span>
        </label>
        <textarea
          id="customNeeds"
          value={customNeeds}
          onChange={(e) => setCustomNeeds(e.target.value)}
          rows={3}
          placeholder="例如：重点关注分布式系统、希望了解二面难度..."
          className="w-full resize-none rounded-md border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-700 focus:border-cyan-500/40"
        />
      </div>

      <button
        type="submit"
        className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-cyan-500"
      >
        <Search className="h-4 w-4" />
        开始搜索
      </button>
    </form>
  );
}
