"use client";

import { useState, type KeyboardEvent } from "react";
import { Building2, ChevronDown, ChevronRight, Plus, X } from "lucide-react";

/**
 * 公司分组选择器 — 按"大厂 / AI 公司 / 外企"分组展示预设公司标签。
 *
 * 设计意图：
 * - PRD 4.4 要求公司选择支持分组预设 + 自定义输入
 * - 上限 5 家公司，达到上限后预设 Tag 禁用
 * - 已选公司统一展示在顶部，不区分预设/自定义来源
 * - 底部保留手动输入框，回车添加自定义公司
 */

const MAX_COMPANIES = 5;

interface CompanyGroup {
  label: string;
  companies: string[];
}

const COMPANY_GROUPS: CompanyGroup[] = [
  {
    label: "大厂",
    companies: ["字节跳动", "阿里巴巴", "腾讯", "美团", "京东", "百度", "华为", "小红书"],
  },
  {
    label: "AI 公司",
    companies: ["商汤", "旷视", "智谱", "月之暗面", "MiniMax", "DeepSeek"],
  },
  {
    label: "外企",
    companies: ["Google", "Microsoft", "Amazon", "Apple"],
  },
];

interface CompanyGroupSelectorProps {
  selected: string[];
  onChange: (companies: string[]) => void;
}

export function CompanyGroupSelector({ selected, onChange }: CompanyGroupSelectorProps) {
  const [input, setInput] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const atLimit = selected.length >= MAX_COMPANIES;

  const toggleCompany = (company: string) => {
    if (selected.includes(company)) {
      onChange(selected.filter((c) => c !== company));
    } else if (!atLimit) {
      onChange([...selected, company]);
    }
  };

  const addCustom = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || selected.includes(trimmed) || atLimit) return;
    onChange([...selected, trimmed]);
    setInput("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      addCustom(input);
    }
    if (event.key === "Backspace" && !input && selected.length > 0) {
      onChange(selected.slice(0, -1));
    }
  };

  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  // 判断一个公司名是否在预设列表中
  const allPresetCompanies = new Set(COMPANY_GROUPS.flatMap((g) => g.companies));
  const customSelected = selected.filter((c) => !allPresetCompanies.has(c));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-slate-700">
          目标公司
        </label>
        <span className={`text-xs tabular-nums ${atLimit ? "font-semibold text-amber-600" : "text-slate-400"}`}>
          {selected.length}/{MAX_COMPANIES}
        </span>
      </div>

      {/* 已选公司 */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((company) => (
            <span
              key={company}
              className="inline-flex items-center gap-1 rounded-md bg-teal-50 border border-teal-200 px-2.5 py-1 text-xs font-medium text-teal-800"
            >
              <Building2 className="h-3 w-3 text-teal-600" />
              {company}
              <button
                type="button"
                onClick={() => onChange(selected.filter((c) => c !== company))}
                className="ml-0.5 rounded p-0.5 transition hover:bg-teal-100"
                aria-label={`移除 ${company}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 分组预设 */}
      <div className="rounded-md border border-slate-200 bg-slate-50/50">
        {COMPANY_GROUPS.map((group, groupIndex) => {
          const isCollapsed = collapsedGroups.has(group.label);
          return (
            <div
              key={group.label}
              className={groupIndex > 0 ? "border-t border-slate-200" : ""}
            >
              <button
                type="button"
                onClick={() => toggleGroup(group.label)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 transition hover:text-slate-700"
              >
                {isCollapsed ? (
                  <ChevronRight className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
                {group.label}
                <span className="ml-auto font-normal tabular-nums text-slate-400">
                  {group.companies.filter((c) => selected.includes(c)).length}/{group.companies.length}
                </span>
              </button>

              {!isCollapsed && (
                <div className="flex flex-wrap gap-1.5 px-3 pb-2.5">
                  {group.companies.map((company) => {
                    const isSelected = selected.includes(company);
                    const isDisabled = atLimit && !isSelected;
                    return (
                      <button
                        key={company}
                        type="button"
                        onClick={() => toggleCompany(company)}
                        disabled={isDisabled}
                        className={`rounded-md border px-2.5 py-1 text-xs font-medium transition ${
                          isSelected
                            ? "border-teal-300 bg-teal-600 text-white shadow-sm"
                            : isDisabled
                              ? "cursor-not-allowed border-slate-200 bg-white text-slate-300"
                              : "border-slate-200 bg-white text-slate-600 hover:border-teal-300 hover:text-teal-700"
                        }`}
                      >
                        {company}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 自定义输入 */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => input && addCustom(input)}
            disabled={atLimit}
            placeholder={atLimit ? `已达上限 ${MAX_COMPANIES} 家` : "输入其他公司名，回车添加"}
            className="w-full rounded-md border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
          />
          {input && !atLimit && (
            <button
              type="button"
              onClick={() => addCustom(input)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 transition hover:text-teal-600"
              aria-label="添加公司"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* 已添加的自定义公司提示 */}
      {customSelected.length > 0 && (
        <p className="text-[10px] text-slate-400">
          自定义添加：{customSelected.join("、")}
        </p>
      )}
    </div>
  );
}
