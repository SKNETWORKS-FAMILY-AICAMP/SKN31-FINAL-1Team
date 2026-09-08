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

  // reqDef/hasConfirmedTasks를 안 넘긴 옛 호출부는 이전과 동일하게 항상 false다
  // (하위 호환) — 아래 별도 테스트에서 실제 reqDef 승인/업무배분 확정 케이스를 본다.
  it("is false for reqSpec and taskAssignment when reqDef/hasConfirmedTasks are omitted", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stepDone(approved, "reqSpec")).toBe(false);
    expect(stepDone(approved, "taskAssignment")).toBe(false);
  });

  it("is true for reqSpec once the requirement definition is approved", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stepDone(approved, "reqSpec", { status_info: { code_id: "APPROVED" } })).toBe(true);
    expect(stepDone(approved, "reqSpec", { status_info: { code_id: "PENDING_REVIEW" } })).toBe(false);
  });

  it("is true for taskAssignment once there's at least one confirmed task", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stepDone(approved, "taskAssignment", null, true)).toBe(true);
    expect(stepDone(approved, "taskAssignment", null, false)).toBe(false);
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

  it("stays on reqSpec once approved but before any task is confirmed", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stageOf(approved, { status_info: { code_id: "APPROVED" } }, false)).toBe("reqSpec");
  });

  it("moves to taskAssignment once the requirement definition is approved and a task is confirmed", () => {
    const approved = specWith("PROPOSAL_APPROVED");
    expect(stageOf(approved, { status_info: { code_id: "APPROVED" } }, true)).toBe("taskAssignment");
  });
});
