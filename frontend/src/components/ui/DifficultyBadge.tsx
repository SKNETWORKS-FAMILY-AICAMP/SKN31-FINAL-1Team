import { cn } from "@/lib/utils";

// 요구사항정의서→업무 분해 에이전트(extract-tasks)가 매기는 난이도 배지. HIGH/MEDIUM/LOW 외
// 값(레거시 목업 라우트의 "HARD" 등, 혹은 아직 난이도가 채워지지 않은 옛 업무)이 들어와도
// 화면이 깨지지 않도록 모르는 값이면 배지 자체를 숨긴다.
const DIFFICULTY_LABEL: Record<string, string> = { HIGH: "상", MEDIUM: "중", LOW: "하" };
const DIFFICULTY_CLASS: Record<string, string> = {
  HIGH: "bg-red-500/10 text-red-500",
  MEDIUM: "bg-amber-500/10 text-amber-500",
  LOW: "bg-slate-500/10 text-slate-500",
};

export function DifficultyBadge({ difficulty, reason }: { difficulty: string | null | undefined; reason?: string | null }) {
  if (!difficulty || !DIFFICULTY_LABEL[difficulty]) return null;
  return (
    <span
      title={reason ?? undefined}
      className={cn("shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-semibold", DIFFICULTY_CLASS[difficulty])}
    >
      난이도 {DIFFICULTY_LABEL[difficulty]}
    </span>
  );
}
