import { Bot, MessageCircle, Star } from "lucide-react";
import type { InterviewQuestion } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/format";
import { EvidenceHighlight } from "./evidence-highlight";

interface QuestionCardProps {
  question: InterviewQuestion;
  index: number;
}

function DifficultyStars({ difficulty }: { difficulty?: number | null }) {
  const level = Math.min(5, Math.max(0, difficulty ?? 0));
  return (
    <div className="flex items-center gap-0.5" aria-label={`难度 ${level} 星`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className={`h-3 w-3 ${i < level ? "fill-amber-400 text-amber-400" : "text-zinc-800"}`} />
      ))}
    </div>
  );
}

export function QuestionCard({ question, index }: QuestionCardProps) {
  const isReal = question.sourceType === "real_interview";
  const categoryLabel = CATEGORY_LABELS[question.category ?? ""] ?? question.category ?? "未分类";

  return (
    <article className="rounded border border-zinc-800/40 bg-zinc-900/30 p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-zinc-800 text-[10px] font-semibold text-zinc-500">
            {index + 1}
          </span>
          <p className="text-sm leading-relaxed text-zinc-200">{question.text}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 pl-9">
        <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{categoryLabel}</span>
        <DifficultyStars difficulty={question.difficulty} />
        <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${isReal ? "bg-cyan-500/10 text-cyan-400" : "bg-amber-500/10 text-amber-400"}`}>
          {isReal ? <MessageCircle className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
          {isReal ? "真实面经" : "AI 延伸"}
        </span>
      </div>
      <div className="pl-9">
        <EvidenceHighlight evidence={question.evidence} />
      </div>
      {question.followUps && question.followUps.length > 0 && (
        <div className="mt-3 pl-9">
          <p className="mb-1 text-[10px] text-zinc-600">可能的追问</p>
          <ul className="space-y-0.5">
            {question.followUps.map((followUp, i) => (
              <li key={i} className="text-xs text-zinc-500 before:mr-2 before:text-zinc-700 before:content-['→']">{followUp}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
