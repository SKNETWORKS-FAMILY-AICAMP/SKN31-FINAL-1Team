import { describe, it, expect, vi, afterEach } from "vitest";
import { isTaskOverdue } from "./taskOverdue";

describe("isTaskOverdue", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns false when there is no due date", () => {
    expect(isTaskOverdue({ wbsEnd: null, status: "IN_PROGRESS" })).toBe(false);
  });

  it.each(["DONE", "CANCELLED", "COMPLETED", "REJECTED"])(
    "returns false for finished status %s even if the due date has passed",
    (status) => {
      expect(isTaskOverdue({ wbsEnd: "2020-01-01", status })).toBe(false);
    }
  );

  it("returns true once a day has fully passed after the due date", () => {
    vi.setSystemTime(new Date("2026-09-10T00:00:00Z"));
    expect(isTaskOverdue({ wbsEnd: "2026-09-09", status: "IN_PROGRESS" })).toBe(true);
  });

  // 회귀 테스트: 마감일 당일 자정(UTC) 직후에는 아직 지연이 아니어야 한다.
  // 실제로 이 경계값 버그 때문에 "오늘이 마감인 업무"가 자정 넘자마자 지연 뱃지가
  // 잘못 붙는 문제가 있었다(lib/taskOverdue.ts 주석 참고) — 재발 방지용.
  it("does not treat the due date itself as overdue right after UTC midnight", () => {
    vi.setSystemTime(new Date("2026-09-09T00:00:01Z"));
    expect(isTaskOverdue({ wbsEnd: "2026-09-09", status: "IN_PROGRESS" })).toBe(false);
  });

  it("is not overdue while the due date is still in the future", () => {
    vi.setSystemTime(new Date("2026-09-01T12:00:00Z"));
    expect(isTaskOverdue({ wbsEnd: "2026-09-09", status: "IN_PROGRESS" })).toBe(false);
  });
});
