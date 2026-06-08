import { Quote } from "lucide-react";
import type { QuestionEvidence } from "@/lib/types";
import { formatPercent } from "@/lib/format";

interface EvidenceHighlightProps {
  evidence?: QuestionEvidence | null;
}

export function EvidenceHighlight({ evidence }: EvidenceHighlightProps) {
  if (!evidence?.quote) return null;

  return (
    <div className="mt-2.5 rounded border border-zinc-800/40 bg-zinc-900/20 px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-2 text-[10px] text-zinc-500">
        <Quote className="h-3 w-3" aria-hidden="true" />
        原文证据
        {evidence.confidence != null && <span className="text-zinc-600">{formatPercent(evidence.confidence)}</span>}
      </div>
      <p className="border-l-2 border-cyan-500/30 pl-3 text-xs leading-relaxed text-zinc-400">
        「{evidence.quote}」
      </p>
      {evidence.sourceUrl && (
        <a href={evidence.sourceUrl} target="_blank" rel="noopener noreferrer" className="mt-1.5 inline-block text-[10px] text-zinc-600 hover:text-cyan-400">
          查看原文
        </a>
      )}
    </div>
  );
}
