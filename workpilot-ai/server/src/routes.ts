import { seedMembers, store } from "./store.js";
import { HttpError, readJsonBody, Router, sendJson } from "./http.js";
import type { Ctx } from "./http.js";
import type { Project } from "./types.js";
import {
  ai,
  aiProviderName,
  approveTask,
  autoApproveAll,
  completeTask,
  continueProject,
  decomposeProject,
  detectDelaysForAllTasks,
  getProjectOr404,
  getTaskOr404,
  isAiLive,
  projectStateResponse,
  recommendAllForProject,
  rescheduleProject,
  resetDeliverableState,
  resetSuggestState,
  runAutoPipeline,
  sendProgressSignal,
  submitMeeting,
} from "./pipeline.js";
import { nextId } from "./store.js";
import { resetAutopilotState } from "./autopilot.js";

seedMembers();

export function buildRouter(): Router {
  const r = new Router();

  r.get("/api/health", (ctx) =>
    sendJson(ctx.res, 200, { ok: true, now: store.nowIso(), aiLive: isAiLive, aiProvider: aiProviderName })
  );

  r.get("/api/members", (ctx) => sendJson(ctx.res, 200, Array.from(store.members.values())));

  r.get("/api/projects", (ctx) => sendJson(ctx.res, 200, Array.from(store.projects.values())));

  // 1) 업무 요청 접수 + 분석 (기획안 5.1) — 이후 분해/추천/승인까지 전부 자동 연쇄된다.
  // body.autoPilot=false 를 주면 예전처럼 분석까지만 하고 수동 버튼으로 단계별 진행 가능.
  r.post("/api/requests", async (ctx) => {
    const body = ctx.body as { text?: string; stack?: string[]; name?: string; autoPilot?: boolean };
    if (!body.text || !body.text.trim()) throw new HttpError(400, "text is required");

    const teamSkills = Array.from(new Set(Array.from(store.members.values()).flatMap((m) => m.skills)));
    const analysis = await ai.analyzeRequest(body.text, { stack: body.stack ?? [], teamSkills });

    const project: Project = {
      id: nextId("proj"),
      name: body.name?.trim() || body.text.trim().slice(0, 24),
      stack: body.stack ?? [],
      createdAt: store.nowIso(),
      requestText: body.text,
      analysis,
    };
    store.projects.set(project.id, project);

    if (body.autoPilot !== false) {
      await runAutoPipeline(project);
    }

    sendJson(ctx.res, 201, projectStateResponse(project.id));
  });

  // 아래 수동 엔드포인트들은 자동 파이프라인이 이미 다 처리하지만, 데모/디버깅/PM의
  // 수동 개입(재배정 등)을 위해 그대로 남겨둔다.

  r.post("/api/projects/:id/decompose", async (ctx) => {
    const project = getProjectOr404(ctx.params.id!);
    await decomposeProject(project);
    sendJson(ctx.res, 201, projectStateResponse(project.id));
  });

  r.post("/api/projects/:id/recommend-all", async (ctx) => {
    const project = getProjectOr404(ctx.params.id!);
    await recommendAllForProject(project);
    sendJson(ctx.res, 200, projectStateResponse(project.id));
  });

  r.post("/api/tasks/:id/approve", async (ctx) => {
    const task = getTaskOr404(ctx.params.id!);
    const body = ctx.body as { memberId?: string };
    approveTask(task, body.memberId);
    sendJson(ctx.res, 200, projectStateResponse(task.projectId));
  });

  r.post("/api/tasks/:id/reject", (ctx) => {
    const task = getTaskOr404(ctx.params.id!);
    task.status = "pending";
    task.recommendation = undefined;
    task.assigneeId = undefined;
    rescheduleProject(task.projectId);
    sendJson(ctx.res, 200, projectStateResponse(task.projectId));
  });

  r.post("/api/tasks/:id/progress", async (ctx) => {
    const task = getTaskOr404(ctx.params.id!);
    const body = ctx.body as { note?: string; source?: "manual" | "git" | "pr" | "ci" };
    sendProgressSignal(task, body.source ?? "manual", body.note);
    sendJson(ctx.res, 200, projectStateResponse(task.projectId));
  });

  r.post("/api/tasks/:id/complete", (ctx) => {
    const task = getTaskOr404(ctx.params.id!);
    completeTask(task);
    sendJson(ctx.res, 200, projectStateResponse(task.projectId));
  });

  // 데모/테스트용 가상 시계 수동 전진 (오토파일럿이 이미 자동으로 시계를 돌리지만,
  // 빨리 감기가 필요할 때 쓸 수 있게 남겨둔다).
  r.post("/api/simulate/advance", async (ctx) => {
    const body = ctx.body as { hours?: number };
    const hours = Number(body.hours ?? 24);
    store.clockOffsetMs += hours * 3600_000;
    const newAlerts = await detectDelaysForAllTasks();
    sendJson(ctx.res, 200, { now: store.nowIso(), newAlerts });
  });

  r.post("/api/alerts/:id/ack", (ctx) => {
    const alert = store.alerts.get(ctx.params.id!);
    if (!alert) throw new HttpError(404, "alert not found");
    alert.status = "acknowledged";
    sendJson(ctx.res, 200, alert);
  });

  r.post("/api/alerts/:id/resolve", (ctx) => {
    const alert = store.alerts.get(ctx.params.id!);
    if (!alert) throw new HttpError(404, "alert not found");
    alert.status = "resolved";
    const task = store.tasks.get(alert.taskId);
    if (task && task.status === "delayed") task.status = "active";
    sendJson(ctx.res, 200, alert);
  });

  // 7) 회의 요약 (기획안 5.7) — 액션 아이템을 신규 Task로 자동 반영 + 추천/승인까지 자동 진행.
  r.post("/api/meetings", async (ctx) => {
    const body = ctx.body as { projectId?: string; text?: string };
    if (!body.projectId || !body.text) throw new HttpError(400, "projectId and text are required");
    const project = getProjectOr404(body.projectId);
    const { note, newTasks } = await submitMeeting(project, body.text);
    sendJson(ctx.res, 201, { note, newTasks, ...projectStateResponse(project.id) });
  });

  r.get("/api/projects/:id", (ctx) => {
    sendJson(ctx.res, 200, projectStateResponse(ctx.params.id!));
  });

  // 프로젝트가 다 끝난 뒤 AI 제안을 클릭하거나 직접 타이핑해서 같은 프로젝트에 다음 라운드를 이어붙인다.
  r.post("/api/projects/:id/continue", async (ctx) => {
    const project = getProjectOr404(ctx.params.id!);
    const body = ctx.body as { text?: string };
    if (!body.text || !body.text.trim()) throw new HttpError(400, "text is required");
    await continueProject(project, body.text.trim());
    sendJson(ctx.res, 201, projectStateResponse(project.id));
  });

  r.post("/api/reset", (ctx) => {
    store.reset();
    resetAutopilotState();
    resetDeliverableState();
    resetSuggestState();
    for (const m of store.members.values()) m.currentLoadHours = 0;
    sendJson(ctx.res, 200, { ok: true });
  });

  // 특정 프로젝트의 승인 대기 작업을 즉시 전부 자동 승인 (수동 개입 없이 진행시키고 싶을 때).
  r.post("/api/projects/:id/auto-approve", (ctx) => {
    const project = getProjectOr404(ctx.params.id!);
    autoApproveAll(project);
    sendJson(ctx.res, 200, projectStateResponse(project.id));
  });

  return r;
}

export async function withParsedBody(ctx: Ctx, fn: (ctx: Ctx) => void | Promise<void>) {
  if (ctx.req.method === "POST") {
    ctx.body = await readJsonBody(ctx.req);
  }
  await fn(ctx);
}
