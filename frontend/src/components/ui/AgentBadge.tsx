import { cn } from "@/lib/utils";

// AI가 실행되는 액션 버튼/라벨에 붙는 작은 배지 — 어떤 에이전트가 이 작업을 하는지 한눈에
// 구분할 수 있도록 에이전트 3종(기획서/요구사항정의서/업무분배)마다 고유한 색을 준다.
// 불투명한 색을 쓰기 때문에 파란 버튼, 빨간(반려) 버튼, 카드 배경 등 어디에 놓여도 잘 보인다.
// 상태 배지(초안=무채색, 검토중=주황, 승인=에메랄드, 반려=빨강)와 겹치지 않는 색을 골랐다.
export type AgentKind = "proposal" | "reqSpec" | "taskAssign";

const AGENT_META: Record<AgentKind, { label: string; className: string }> = {
  proposal: { label: "기획서", className: "bg-blue-500 text-white" },
  reqSpec: { label: "요구사항정의서", className: "bg-violet-500 text-white" },
  taskAssign: { label: "업무 배분", className: "bg-teal-500 text-white" },
};

export function AgentBadge({ agent = "proposal" }: { agent?: AgentKind }) {
  const meta = AGENT_META[agent];
  return (
    <span className={cn(
      "inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider leading-none whitespace-nowrap",
      meta.className
    )}>
      {meta.label} Agent
    </span>
  );
}
