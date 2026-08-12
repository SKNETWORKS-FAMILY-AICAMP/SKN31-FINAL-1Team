import type { Task } from "./types.js";

// ── 일정 생성 (기획안 5.4절) ─────────────────────────────────────────
// 단순화된 Critical-Path 계산: Task 의존관계 + 담당자별 순차 큐를 고려해
// plannedStart/plannedEnd를 산출한다.
// MVP 단순화를 위해 "1 작업시간 = 1 시간(wall-clock)"으로 취급한다.
// (실제 서비스에서는 8h/day 근무시간, 휴가/캘린더 반영이 필요 — 기획안 5.4/리스크 참조)

function topoSort(tasks: Task[]): Task[] {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const indegree = new Map<string, number>();
  const dependents = new Map<string, string[]>();

  for (const t of tasks) {
    indegree.set(t.id, 0);
    dependents.set(t.id, []);
  }
  for (const t of tasks) {
    for (const depId of t.dependsOn) {
      if (!byId.has(depId)) continue;
      indegree.set(t.id, (indegree.get(t.id) ?? 0) + 1);
      dependents.get(depId)!.push(t.id);
    }
  }

  const queue = tasks.filter((t) => (indegree.get(t.id) ?? 0) === 0).map((t) => t.id);
  const order: Task[] = [];
  const visited = new Set<string>();

  while (queue.length > 0) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    order.push(byId.get(id)!);
    for (const depId of dependents.get(id) ?? []) {
      indegree.set(depId, (indegree.get(depId) ?? 1) - 1);
      if ((indegree.get(depId) ?? 0) <= 0) queue.push(depId);
    }
  }

  // 사이클 등으로 못 돈 나머지는 원래 순서대로 뒤에 붙인다(방어적 처리).
  for (const t of tasks) {
    if (!visited.has(t.id)) order.push(t);
  }
  return order;
}

export function computeSchedule(allTasks: Task[], nowIso: string): void {
  const byId = new Map(allTasks.map((t) => [t.id, t]));
  const memberNextAvailable = new Map<string, number>();
  const now = new Date(nowIso).getTime();
  const order = topoSort(allTasks);

  for (const task of order) {
    if (!task.assigneeId) {
      task.plannedStart = undefined;
      task.plannedEnd = undefined;
      continue;
    }
    if (task.status === "done" && task.actualEnd) {
      memberNextAvailable.set(
        task.assigneeId,
        Math.max(
          memberNextAvailable.get(task.assigneeId) ?? 0,
          new Date(task.actualEnd).getTime()
        )
      );
      continue;
    }

    const depEndTimes = task.dependsOn.map((depId) => {
      const dep = byId.get(depId);
      if (!dep) return now;
      const endIso = dep.actualEnd ?? dep.plannedEnd;
      return endIso ? new Date(endIso).getTime() : now;
    });
    const depReady = depEndTimes.length > 0 ? Math.max(...depEndTimes) : now;
    const assigneeReady = memberNextAvailable.get(task.assigneeId) ?? now;
    const startMs = task.actualStart
      ? new Date(task.actualStart).getTime()
      : Math.max(depReady, assigneeReady, now);
    const durationMs = task.estimateHours * 3600_000;
    const endMs = startMs + durationMs;

    task.plannedStart = new Date(startMs).toISOString();
    task.plannedEnd = new Date(endMs).toISOString();
    memberNextAvailable.set(task.assigneeId, endMs);
  }
}
