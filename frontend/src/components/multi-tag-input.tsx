"use client";

import { useState, type KeyboardEvent } from "react";
import { Plus, X } from "lucide-react";

interface MultiTagInputProps {
  label: string;
  placeholder: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  suggestions?: string[];
}

export function MultiTagInput({
  label,
  placeholder,
  tags,
  onChange,
  suggestions = [],
}: MultiTagInputProps) {
  const [input, setInput] = useState("");

  const addTag = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || tags.includes(trimmed)) return;
    onChange([...tags, trimmed]);
    setInput("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      addTag(input);
    }
    if (event.key === "Backspace" && !input && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div className="space-y-2">
      <label className="block text-sm text-zinc-400">{label}</label>
      <div className="rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 focus-within:border-cyan-500/40">
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-300"
            >
              {tag}
              <button
                type="button"
                onClick={() => onChange(tags.filter((t) => t !== tag))}
                className="rounded p-0.5 hover:bg-cyan-500/20"
                aria-label={`移除 ${tag}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => input && addTag(input)}
            placeholder={tags.length === 0 ? placeholder : "继续添加..."}
            className="min-w-[120px] flex-1 bg-transparent py-1 text-sm text-zinc-100 outline-none placeholder:text-zinc-700"
          />
        </div>
      </div>
      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {suggestions
            .filter((s) => !tags.includes(s))
            .slice(0, 6)
            .map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => addTag(suggestion)}
                className="inline-flex items-center gap-1 rounded border border-zinc-800 px-2 py-0.5 text-xs text-zinc-500 transition hover:border-cyan-500/30 hover:text-cyan-400"
              >
                <Plus className="h-3 w-3" />
                {suggestion}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
