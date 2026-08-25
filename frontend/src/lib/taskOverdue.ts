// 마감일(wbsEnd)이 지났는데도 완료/취소되지 않은 업무를 "지연"으로 판단한다.
// 클라이언트(뱃지 표시)와 서버(알림 발송 대상 판단, overdueCheck.ts의 SQL) 양쪽에서 같은 기준을
// 써야 하므로 공유 함수로 뺀다.
// wbsEnd는 "그날 00:00 UTC"로 저장돼 있다(assign-tasks route의 toDateStr 참고) — 그래서
// 단순히 now()와 비교하면 마감일 당일 자정(UTC)이 지나자마자 아직 하루가 남았는데도 "지연"으로
// 잘못 표시된다(실제로 발견됨: 오늘이 마감인 업무가 자정 직후부터 지연 뱃지가 붙어 있었음).
// 마감일 당일은 하루를 통째로 인정해주고, 그 다음 날 UTC 자정부터만 지연으로 본다.
export function isTaskOverdue(task: { wbsEnd: string | Date | null; status: string }): boolean {
  if (!task.wbsEnd) return false;
  if (task.status === "DONE" || task.status === "CANCELLED") return false;
  const todayUtcMidnight = new Date();
  todayUtcMidnight.setUTCHours(0, 0, 0, 0);
  return new Date(task.wbsEnd) < todayUtcMidnight;
}
