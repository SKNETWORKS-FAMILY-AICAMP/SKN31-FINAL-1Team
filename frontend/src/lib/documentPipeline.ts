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

// 기획서는 승인 여부로 "완료"가 명확하다. 요구사항정의서·업무배분은 이 프로젝트에 아직
// 승인 워크플로우 자체가 없어서(백엔드에 status 필드가 없음) "완료"라는 개념이 없다 —
// heyzzabi2의 업무배분 단계와 같은 취급(항상 false, 잠기지 않음).
export function stepDone(spec: SpecLike, step: PipelineTab): boolean {
  return step === "proposal" ? bareStatus(spec) === "APPROVED" : false;
}

// 문서를 고르면 "그 문서가 지금 있는 단계"를 첫 화면으로 보여준다 — 요구사항정의서
// 승인 개념이 없으므로, 기획서가 승인되면 그 다음 할 일인 요구사항정의서 단계로 고정한다.
export function stageOf(spec: SpecLike): PipelineTab {
  return bareStatus(spec) === "APPROVED" ? "reqSpec" : "proposal";
}
