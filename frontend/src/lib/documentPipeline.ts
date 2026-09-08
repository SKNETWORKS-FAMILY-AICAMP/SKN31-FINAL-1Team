// 문서생성 화면의 파이프라인(기획서 → 요구사항정의서 → 업무배분) 상태 판단 로직.
// documents/page.tsx에서 쓰던 순수 함수를 테스트 가능하게 여기로 뺐다 — heyzzabi2(구버전
// 프로토타입)의 파이프라인 스테퍼와 같은 구조를 따른다.

export type BareStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";

// 백엔드 CommonCode.code_id는 그룹 간 전역 유일해야 해서 "PROPOSAL_" 접두사가 붙어 있다
// (REQSPEC_STATUS 등 다른 그룹과 값이 겹치지 않도록) — 화면 표시/비교에서는 벗겨서 쓴다.
export function bareStatus(spec: { status_info?: { code_id?: string | null } | null } | null): BareStatus {
  return ((spec?.status_info?.code_id ?? "").replace(/^PROPOSAL_/, "") || "DRAFT") as BareStatus;
}

export type PipelineTab = "proposal" | "reqSpec" | "taskAssignment";
export const PIPELINE_STEPS: PipelineTab[] = ["proposal", "reqSpec", "taskAssignment"];
export const PIPELINE_TAB_LABEL: Record<PipelineTab, string> = {
  proposal: "기획서", reqSpec: "요구사항정의서", taskAssignment: "업무 배분",
};

type SpecLike = { status_info?: { code_id?: string | null } | null } | null;
type ReqDefLike = { status_info?: { code_id?: string | null } | null } | null;

// 요구사항정의서는 이제(2026-09) DRAFT/PENDING_REVIEW/APPROVED/REJECTED 승인
// 워크플로우가 생겼고, 업무배분은 확정된 TaskAssignment가 하나라도 있으면 "완료"로
// 본다 — 이 프로젝트엔 업무배분 자체에 별도 승인 상태가 없어(확정 = 완료) 그렇다.
// reqDef/hasConfirmedTasks를 안 넘기면(예: 옛 호출부·테스트) 이전과 동일하게
// false로 취급된다 — 하위 호환을 위해 둘 다 선택 인자로 둔다.
export function stepDone(
  spec: SpecLike,
  step: PipelineTab,
  reqDef?: ReqDefLike,
  hasConfirmedTasks?: boolean,
): boolean {
  if (step === "proposal") return bareStatus(spec) === "APPROVED";
  if (step === "reqSpec") return reqDef?.status_info?.code_id === "APPROVED";
  return !!hasConfirmedTasks; // step === "taskAssignment"
}

// 문서를 고르면 "그 문서가 지금 있는 단계"를 첫 화면으로 보여준다. 예전엔 기획서
// 승인 이후를 전부 "reqSpec"으로 뭉뚱그렸는데(요구사항정의서 승인 개념이 아직
// 없었을 때 결정), 지금은 승인 워크플로우와 업무배분 확정까지 생겨서 문서가 실제로
// 끝까지 진행됐는데도 목록/스테퍼가 "요구사항정의서" 단계에 멈춰 보이는 문제가
// 있었다 — reqDef/hasConfirmedTasks가 있으면 그만큼 더 뒤 단계로 보여준다.
export function stageOf(spec: SpecLike, reqDef?: ReqDefLike, hasConfirmedTasks?: boolean): PipelineTab {
  if (reqDef?.status_info?.code_id === "APPROVED" && hasConfirmedTasks) return "taskAssignment";
  if (bareStatus(spec) === "APPROVED") return "reqSpec";
  return "proposal";
}
