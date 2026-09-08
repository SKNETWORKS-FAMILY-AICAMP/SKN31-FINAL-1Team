import { describe, it, expect } from "vitest";
import { bareStatus, stepDone, stageOf } from "./documentPipeline";

const specWith = (codeId: string | null) => (codeId ? { status_info: { code_id: codeId } } : null);

describe("bareStatus", () => {
  it("returns DRAFT when spec is null", () => {
    expect(bareStatus(null)).toBe("DRAFT");
  });

  it("returns DRAFT when status_info is missing", () => {
    expect(bareStatus({ status_info: null })).toBe("DRAFT");
  });

  // 백엔드 CommonCode.code_id는 그룹 간 전역 유일해야 해서 PROPOSAL_ 접두사가 붙는다 —
  // 화면 비교 로직은 그 접두사를 모르는 채로 값만 비교해야 한다.
  it.each([
    ["PROPOSAL_DRAFT", "DRAFT"],
    ["PROPOSAL_PENDING_REVIEW", "PENDING_REVIEW"],
    ["PROPOSAL_APPROVED", "APPROVED"],
    ["PROPOSAL_REJECTED", "REJECTED"],
  ])("strips the PROPOSAL_ prefix from %s", (codeId, expected) => {
    expect(bareStatus(specWith(codeId))).toBe(expected);
  });
});

describe("stepDone", () => {
  it("is true for the proposal step only when the spec is approved", () => {
    expect(stepDone(specWith("PROPOSAL_APPROVED"), "proposal")).toBe(true);
    expect(stepDone(specWith("PROPOSAL_PENDING_REVIEW"), "proposal")).toBe(false);
    expect(stepDone(null, "proposal")).toBe(false);
  });

  // 요구사항정의서/업무배분은 이 프로젝트에 승인 워크플로우 자체가 없어서(백엔드 status
  // 필드 없음) "완료"라는 개념이 없다 — 기획서가 승인되어도 항상 false여야 한다(잠기지 않음).
  it("is always false for reqSpec and taskAssignment regardless of proposal status", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stepDone(approved, "reqSpec")).toBe(false);
    expect(stepDone(approved, "taskAssignment")).toBe(false);
  });
});

describe("stageOf", () => {
  it("stays on proposal while the spec is not approved", () => {
    expect(stageOf(null)).toBe("proposal");
    expect(stageOf(specWith("PROPOSAL_DRAFT"))).toBe("proposal");
    expect(stageOf(specWith("PROPOSAL_PENDING_REVIEW"))).toBe("proposal");
    expect(stageOf(specWith("PROPOSAL_REJECTED"))).toBe("proposal");
  });

  it("moves to reqSpec once the proposal is approved", () => {
    expect(stageOf(specWith("PROPOSAL_APPROVED"))).toBe("reqSpec");
  });
});
