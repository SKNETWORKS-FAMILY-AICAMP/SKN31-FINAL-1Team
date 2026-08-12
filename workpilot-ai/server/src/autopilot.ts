import { store } from "./store.js";
import { completeTask, detectDelaysForAllTasks, sendProgressSignal } from "./pipeline.js";
import type { Task } from "./types.js";

// ── 오토파일럿 ───────────────────────────────────────────────────────
// "PM은 최초 업무 지시만 하고, 그 이후로는 모든 것이 자동으로 진행된다"는
// 요구사항의 핵심 구현체. 배정까지 끝난 작업을 실제 개발자가 진행하는 것처럼
// 자동으로 착수(진행 신호) -> 완료 처리하고, 그 과정에서 가상 시계를 실제보다
// 훨씬 빠르게 흘려보내 지연도 자연스럽게 발생/감지되게 한다.
//
// 데모/시연이 목적이므로 완료 소요시간에 약간의 무작위성(0.7x~1.5x)을 줘서
// 일부 작업은 예상 기한(plannedEnd)을 넘기게 만든다 — 그래야 지연 알림 파이프라인이
// 매번 아무 일도 없이 지나가지 않고 실제로 동작하는 걸 볼 수 있다.

const durationMultiplier = new Map<string, number>();

function isReady(task: Task): boolean {
  if (task.dependsOn.length === 0) return true;
  return task.dependsOn.every((depId) => store.tasks.get(depId)?.status === "done");
}

function pickMultiplier(): number {
  // 0.7x(예상보다 빠름) ~ 1.5x(지연) 사이, 평균은 1.0 근처보다 살짝 낮게.
  return 0.7 + Math.random() * 0.8;
}

async function tick(virtualHoursPerTick: number): Promise<void> {
  store.clockOffsetMs += virtualHoursPerTick * 3600_000;
  const nowMs = Date.now() + store.clockOffsetMs;

  for (const task of store.tasks.values()) {
    if (task.status === "assigned" && isReady(task)) {
      sendProgressSignal(task, "ci", "자동 착수(오토파일럿)");
      durationMultiplier.set(task.id, pickMultiplier());
      continue;
    }

    if (task.status === "active" || task.status === "delayed") {
      const start = task.actualStart ? new Date(task.actualStart).getTime() : nowMs;
      const mult = durationMultiplier.get(task.id) ?? 1;
      const durationMs = task.estimateHours * mult * 3600_000;
      if (nowMs >= start + durationMs) {
        completeTask(task);
        durationMultiplier.delete(task.id);
      }
    }
  }

  await detectDelaysForAllTasks();
}

let timer: ReturnType<typeof setInterval> | undefined;

export function startAutopilot(opts?: { intervalMs?: number; virtualHoursPerTick?: number }) {
  const intervalMs = opts?.intervalMs ?? 4000;
  const virtualHoursPerTick = opts?.virtualHoursPerTick ?? 3;
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    tick(virtualHoursPerTick).catch((err) => console.error("[WorkPilot AI] autopilot tick failed:", err));
  }, intervalMs);
  console.log(
    `[WorkPilot AI] autopilot started (every ${intervalMs}ms, +${virtualHoursPerTick}h virtual time per tick)`
  );
}

export function stopAutopilot() {
  if (timer) clearInterval(timer);
  timer = undefined;
}

export function resetAutopilotState() {
  durationMultiplier.clear();
}
