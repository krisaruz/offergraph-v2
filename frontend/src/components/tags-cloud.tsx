interface TagsCloudProps {
  tags: string[];
}

export function TagsCloud({ tags }: TagsCloudProps) {
  if (tags.length === 0) {
    return (
      <p className="font-mono text-xs text-zinc-600">暂无标签数据</p>
    );
  }

  const maxFreq = Math.max(...tags.map((_, i) => tags.length - i));

  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag, index) => {
        const weight = (tags.length - index) / maxFreq;
        const opacity =
          weight > 0.7
            ? "bg-cyan-500/15 text-cyan-300"
            : weight > 0.4
              ? "bg-zinc-800 text-zinc-400"
              : "bg-zinc-900 text-zinc-500";

        return (
          <span
            key={tag}
            className={`rounded px-2 py-1 font-mono text-[10px] ${opacity}`}
          >
            {tag}
          </span>
        );
      })}
    </div>
  );
}
