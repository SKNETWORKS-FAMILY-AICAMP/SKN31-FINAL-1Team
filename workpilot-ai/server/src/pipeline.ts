import fs from "node:fs";
import path from "node:path";
import { createAIProvider } from "./aiProviderFactory.js";
import type { AIProviderName } from "./aiProviderFactory.js";
import { computeSchedule } from "./scheduler.js";
import { nextId, store } from "./store.js";
import { HttpError } from "./http.js";
import type { AIProvider, DelayAlert, Project, ProgressSignal, Task, TaskDraft } from "./types.js";

// ── 파이프라인 오케스트레이션 ────────────────────────────────────────
// 요청 분석 -> 작업 분해 -> 담당자 추천/승인 -> 일정 계산 -> 진행/지연/회의
// 각 단계의 실제 로직을 한 곳에 모아, REST 라우트(routes.ts)와 백그라운드
// 오토파일럿(autopilot.ts)이 동일한 함수를 공유하게 한다. "업무 지시 이외에는
// 모든 것이 자동"이라는 요구사항대로, 이 모듈의 함수들이 자동으로 연쇄 호출된다.

const active = createAIProvider();
export const ai: AIProvider = active.provider;
export const isAiLive: boolean = active.isLive;
export const aiProviderName: AIProviderName = active.name;

export function getProjectOr404(id: string): Project {
  const p = store.projects.get(id);
  if (!p) throw new HttpError(404, `project ${id} not found`);
  return p;
}

export function getTaskOr404(id: string): Task {
  const t = store.tasks.get(id);
  if (!t) throw new HttpError(404, `task ${id} not found`);
  return t;
}

export function recomputeLoads() {
  const loadByMember = new Map<string, number>();
  for (const t of store.tasks.values()) {
    if (!t.assigneeId) continue;
    if (t.status === "done") continue;
    loadByMember.set(t.assigneeId, (loadByMember.get(t.assigneeId) ?? 0) + t.estimateHours);
  }
  for (const m of store.members.values()) {
    m.currentLoadHours = loadByMember.get(m.id) ?? 0;
  }
}

export function rescheduleProject(projectId: string) {
  computeSchedule(store.tasksByProject(projectId), store.nowIso());
}

export function projectStateResponse(projectId: string) {
  const project = getProjectOr404(projectId);
  const tasks = store.tasksByProject(projectId).sort((a, b) => a.id.localeCompare(b.id));
  const taskIds = new Set(tasks.map((t) => t.id));
  const alerts = Array.from(store.alerts.values()).filter((a) => taskIds.has(a.taskId));
  const notes = Array.from(store.notes.values()).filter((n) => n.projectId === projectId);
  const notifications = Array.from(store.notifications.values()).sort((a, b) =>
    b.createdAt.localeCompare(a.createdAt)
  );
  return {
    project,
    tasks,
    members: Array.from(store.members.values()),
    alerts,
    meetingNotes: notes,
    notifications,
    now: store.nowIso(),
  };
}

function draftsToTasks(projectId: string, drafts: TaskDraft[]): Task[] {
  const titleToId = new Map<string, string>();
  for (const t of store.tasksByProject(projectId)) titleToId.set(t.title, t.id);

  const created: Task[] = [];
  for (const d of drafts) {
    const id = nextId("task");
    titleToId.set(d.title, id);
    created.push({
      id,
      projectId,
      title: d.title,
      description: d.description,
      requiredSkills: d.requiredSkills,
      estimateHours: d.estimateHours,
      dependsOn: [],
      status: "pending",
    });
  }
  for (let i = 0; i < drafts.length; i++) {
    const d = drafts[i]!;
    const t = created[i]!;
    t.dependsOn = d.dependsOnTitles.map((title) => titleToId.get(title)).filter((x): x is string => Boolean(x));
  }
  for (const t of created) store.tasks.set(t.id, t);
  return created;
}

/** 분해된 작업이 2개 이상이면, 다른 모든 작업이 끝난 뒤 그 결과물들을 실제로 하나로 잇는
 * "메인 화면/통합 연결" 작업을 자동으로 추가한다. dependsOn을 전체 작업으로 걸어두면
 * 오토파일럿의 의존관계 게이트(isReady) 덕분에 나머지가 다 끝난 뒤에만 착수되고,
 * 그때는 모든 형제 작업의 결과물 요약이 갖춰져 있어 실제로 연결하는 코드를 짤 수 있다. */
function addIntegrationTask(projectId: string, created: Task[]): Task | null {
  if (created.length < 2) return null;
  const id = nextId("task");
  const skills = Array.from(new Set(created.flatMap((t) => t.requiredSkills)));
  const wantsFrontend = skills.includes("Frontend") || skills.includes("UI");
  const task: Task = {
    id,
    projectId,
    title: "메인 화면/통합 연결",
    description:
      "이 프로젝트의 다른 모든 작업 결과물(백엔드 API, DB, 화면 등)을 실제로 하나로 잇는 " +
      "메인 진입점 또는 통합 화면을 만든다. 각 작업의 요약에 나온 API 경로/컴포넌트를 그대로 사용해서 연결한다.",
    requiredSkills: wantsFrontend ? ["Frontend", "통합"] : ["Backend", "통합"],
    estimateHours: Math.max(6, Math.round(created.reduce((sum, t) => sum + t.estimateHours, 0) * 0.15)),
    dependsOn: created.map((t) => t.id),
    status: "pending",
  };
  store.tasks.set(id, task);
  return task;
}

/** 2) 작업 분해 — 프로젝트 요청 분석 결과를 WBS(Task[])로 만든다. */
export async function decomposeProject(project: Project): Promise<Task[]> {
  if (!project.analysis) throw new HttpError(400, "run analyzeRequest first");
  const drafts = await ai.decomposeIntoTasks(project.analysis);
  const created = draftsToTasks(project.id, drafts);
  const integration = addIntegrationTask(project.id, created);
  if (integration) created.push(integration);
  rescheduleProject(project.id);
  return created;
}

/** 3) 담당자 추천 — 미배정(pending) 작업 전체에 추천안을 붙이고 승인 대기로 전환한다. */
export async function recommendAllForProject(project: Project): Promise<void> {
  const members = Array.from(store.members.values());
  const pending = store.tasksByProject(project.id).filter((t) => t.status === "pending");
  for (const t of pending) {
    t.recommendation = await ai.recommendAssignee({ requiredSkills: t.requiredSkills, title: t.title }, members);
    t.status = "waiting_approval";
  }
  if (pending.length > 0) {
    const lead = members.find((m) => m.isLead);
    if (lead) {
      store.addNotification(
        lead.id,
        "waiting_approval",
        `${project.name}: AI가 담당자 배정안을 추천했습니다 (${pending.length}건).`
      );
    }
  }
}

/** 4) 배정 확정 (승인) — memberId 미지정 시 AI 1순위 추천을 그대로 채택한다. */
export function approveTask(task: Task, memberId?: string): Task {
  const chosen = memberId ?? task.recommendation?.[0]?.memberId;
  if (!chosen) throw new HttpError(400, "no memberId and no recommendation available");
  if (!store.members.has(chosen)) throw new HttpError(404, `member ${chosen} not found`);
  task.assigneeId = chosen;
  task.status = "assigned";
  recomputeLoads();
  rescheduleProject(task.projectId);
  return task;
}

/** 승인 대기 중인 작업 전체를 AI 1순위 추천대로 자동 승인한다 ("업무 지시 이외 전부 자동"). */
export function autoApproveAll(project: Project): void {
  const waiting = store.tasksByProject(project.id).filter((t) => t.status === "waiting_approval");
  for (const t of waiting) {
    try {
      approveTask(t);
    } catch {
      /* 추천안이 없는 예외 케이스는 건너뛴다 — PM이 수동으로 배정 가능 */
    }
  }
}

/** 요청 접수 이후 전체 파이프라인(분해 -> 추천 -> 자동 승인)을 연쇄 실행한다. */
export async function runAutoPipeline(project: Project): Promise<void> {
  await decomposeProject(project);
  await recommendAllForProject(project);
  autoApproveAll(project);
}

/** 5) 진행 신호 — 커밋/PR/CI 또는 오토파일럿의 "작업 시작" 신호. */
export function sendProgressSignal(task: Task, source: ProgressSignal["source"], note?: string): void {
  const signal: ProgressSignal = {
    id: nextId("sig"),
    taskId: task.id,
    source,
    note,
    timestamp: store.nowIso(),
  };
  store.signals.push(signal);
  task.lastSignalAt = signal.timestamp;

  if (task.status === "assigned") {
    task.status = "active";
    task.actualStart = task.actualStart ?? signal.timestamp;
  } else if (task.status === "delayed") {
    task.status = "active";
    for (const alert of store.alerts.values()) {
      if (alert.taskId === task.id && alert.status === "open") alert.status = "resolved";
    }
  }
  rescheduleProject(task.projectId);
  maybeGenerateDeliverable(task);
}

// ── 실제 결과물 생성 ─────────────────────────────────────────────────
// 작업이 착수(active)되는 순간 AI에게 실제로 그 작업을 구현하게 시키고, 결과 파일을
// server/output/<projectId>/ 아래 저장한다. Task에는 파일명 등 경량 메타데이터만 남긴다.
// dist/pipeline.js 기준 ../output = server/output.
const OUTPUT_ROOT = path.resolve(__dirname, "../output");
const deliverableInFlight = new Set<string>();

function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9가-힣]+/g, "-")
      .replace(/(^-|-$)/g, "")
      .slice(0, 50) || "task"
  );
}

async function generateDeliverableForTask(task: Task, project: Project): Promise<void> {
  // 같은 프로젝트에서 이미 결과물이 나온 형제 작업들의 요약 — 다음 작업이 그걸 참고해서
  // 실제로 맞물리는 코드를 짜도록 컨텍스트로 전달한다.
  const siblingDeliverables = store
    .tasksByProject(project.id)
    .filter((t) => t.id !== task.id && t.deliverable?.summary)
    .map((t) => ({ title: t.title, summary: t.deliverable!.summary! }));

  const result = await ai.generateDeliverable(
    { id: task.id, title: task.title, description: task.description, requiredSkills: task.requiredSkills },
    { name: project.name, stack: project.stack },
    siblingDeliverables
  );
  if (!result) return;
  const dir = path.join(OUTPUT_ROOT, project.id);
  fs.mkdirSync(dir, { recursive: true });
  const filename = `${task.id}-${result.filename || `${slugify(task.title)}.txt`}`;
  fs.writeFileSync(path.join(dir, filename), result.content, "utf-8");
  task.deliverable = { filename, language: result.language, generatedAt: store.nowIso(), summary: result.summary };
}

/** active로 전환된 작업에 대해, 아직 결과물이 없고 현재 생성 중도 아닐 때만 트리거한다
 * (자동 진행 신호가 여러 번 와도 중복 API 호출/파일 생성을 하지 않도록 가드). */
export function maybeGenerateDeliverable(task: Task): void {
  if (task.status !== "active") return;
  if (task.deliverable) return;
  if (deliverableInFlight.has(task.id)) return;
  const project = store.projects.get(task.projectId);
  if (!project) return;

  deliverableInFlight.add(task.id);
  generateDeliverableForTask(task, project)
    .catch((err) => console.error(`[WorkPilot AI] deliverable generation failed for task ${task.id}:`, err))
    .finally(() => deliverableInFlight.delete(task.id));
}

export function resetDeliverableState(): void {
  deliverableInFlight.clear();
}

export function completeTask(task: Task): void {
  task.status = "done";
  task.actualEnd = store.nowIso();
  task.actualStart = task.actualStart ?? task.actualEnd;
  for (const alert of store.alerts.values()) {
    if (alert.taskId === task.id && alert.status !== "resolved") alert.status = "resolved";
  }
  recomputeLoads();
  rescheduleProject(task.projectId);
  const lead = Array.from(store.members.values()).find((m) => m.isLead);
  if (lead) store.addNotification(lead.id, "task_done", `"${task.title}" 완료됨.`);

  const project = store.projects.get(task.projectId);
  if (project && isProjectFullyDone(project.id)) {
    maybeSuggestNextSteps(project);
  }
}

// ── 다음 단계 제안 + 이어서 진행 ─────────────────────────────────────
// 프로젝트의 모든 작업이 끝나면(=더 이상 오토파일럿이 할 일이 없으면), 완료된 작업을 근거로
// "다음엔 뭘 하면 좋을지" 몇 가지를 자동으로 제안한다. PM은 그중 하나를 클릭하거나 직접
// 타이핑해서 같은 프로젝트에 새 라운드(분해 -> 통합 작업 -> 추천 -> 자동 승인)를 이어 붙일 수 있다.

function isProjectFullyDone(projectId: string): boolean {
  const tasks = store.tasksByProject(projectId);
  return tasks.length > 0 && tasks.every((t) => t.status === "done");
}

const suggestInFlight = new Set<string>();

function maybeSuggestNextSteps(project: Project): void {
  if (project.nextStepSuggestions) return; // 이미 생성됨(혹은 생성 중 표시 완료)
  if (suggestInFlight.has(project.id)) return;
  suggestInFlight.add(project.id);
  const completed = store
    .tasksByProject(project.id)
    .filter((t) => t.status === "done")
    .map((t) => ({ title: t.title, description: t.description }));

  ai.suggestNextSteps({ name: project.name, requestText: project.requestText, stack: project.stack }, completed)
    .then((suggestions) => {
      project.nextStepSuggestions = suggestions;
    })
    .catch((err) => {
      console.error(`[WorkPilot AI] next-step suggestion failed for project ${project.id}:`, err);
      project.nextStepSuggestions = []; // 실패해도 "생성 중" 상태로 영원히 남지 않게 빈 배열로 확정
    })
    .finally(() => suggestInFlight.delete(project.id));
}

export function resetSuggestState(): void {
  suggestInFlight.clear();
}

/** 완료된 프로젝트에 새 지시를 이어붙인다 — 새 프로젝트를 만들지 않고 같은 프로젝트/팀에
 * 작업을 추가한다(진행 상황 감지를 위해 요청 이력도 requestText에 덧붙여 남긴다). */
export async function continueProject(project: Project, text: string): Promise<Task[]> {
  const teamSkills = Array.from(new Set(Array.from(store.members.values()).flatMap((m) => m.skills)));
  const analysis = await ai.analyzeRequest(text, { stack: project.stack, teamSkills });
  const drafts = await ai.decomposeIntoTasks(analysis);
  const created = draftsToTasks(project.id, drafts);
  const integration = addIntegrationTask(project.id, created);
  if (integration) created.push(integration);

  project.requestText = `${project.requestText}\n→ ${text}`;
  project.nextStepSuggestions = undefined; // 이번 라운드가 끝나면 completeTask에서 다시 채워짐

  await recommendAllForProject(project);
  autoApproveAll(project);
  rescheduleProject(project.id);
  return created;
}

/** 6) 지연 감지 — 전체 작업을 훑어 새 DelayAlert를 만들고 알림을 보낸다. */
export async function detectDelaysForAllTasks(): Promise<DelayAlert[]> {
  const newAlerts: DelayAlert[] = [];
  for (const task of store.tasks.values()) {
    if (task.status === "done" || task.status === "pending" || task.status === "waiting_approval") continue;
    const risk = await ai.analyzeDelayRisk(task, store.signals, store.nowIso());
    if (!risk) continue;
    const alreadyOpen = Array.from(store.alerts.values()).some(
      (a) => a.taskId === task.id && a.reason === risk.reason && a.status === "open"
    );
    if (alreadyOpen) continue;

    const alert: DelayAlert = {
      id: nextId("alert"),
      taskId: task.id,
      detectedAt: store.nowIso(),
      reason: risk.reason,
      message: risk.message,
      proposedAction: risk.proposedAction,
      status: "open",
    };
    store.alerts.set(alert.id, alert);
    newAlerts.push(alert);
    task.status = "delayed";
    if (task.assigneeId) store.addNotification(task.assigneeId, "delay", `"${task.title}": ${risk.message}`);
    const lead = Array.from(store.members.values()).find((m) => m.isLead);
    if (lead) store.addNotification(lead.id, "delay", `"${task.title}" 지연 위험: ${risk.proposedAction}`);
  }
  return newAlerts;
}

/** 7) 회의 요약 — 액션 아이템을 신규 Task로 만들고, 곧바로 추천/자동 승인까지 진행한다. */
export async function submitMeeting(project: Project, rawText: string) {
  const summary = await ai.summarizeMeeting(rawText);
  const note = {
    id: nextId("note"),
    projectId: project.id,
    date: store.nowIso(),
    rawText,
    decisions: summary.decisions,
    actionItems: summary.actionItems,
    risks: summary.risks,
  };
  store.notes.set(note.id, note);

  const newTasks: Task[] = summary.actionItems.map((item) => {
    const t: Task = {
      id: nextId("task"),
      projectId: project.id,
      title: item.slice(0, 60),
      description: `회의 요약에서 자동 생성된 액션 아이템: ${item}`,
      requiredSkills: [],
      estimateHours: 4,
      dependsOn: [],
      status: "pending",
      createdFromMeetingNoteId: note.id,
    };
    store.tasks.set(t.id, t);
    return t;
  });

  const lead = Array.from(store.members.values()).find((m) => m.isLead);
  if (lead) store.addNotification(lead.id, "meeting", `회의 요약 완료: 액션 아이템 ${newTasks.length}건 생성됨.`);

  // 회의에서 나온 신규 작업도 "지시 이외에는 자동"이라는 원칙에 따라 추천/승인까지 이어간다.
  await recommendAllForProject(project);
  autoApproveAll(project);
  rescheduleProject(project.id);

  return { note, newTasks };
}
