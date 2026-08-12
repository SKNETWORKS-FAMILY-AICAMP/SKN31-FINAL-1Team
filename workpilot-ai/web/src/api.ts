import type { DelayAlert, MeetingNote, ProjectState, Task } from "./types.js";

// ── REST API 클라이언트 (같은 오리진에서 서빙되므로 base는 빈 문자열) ──

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    req<{ ok: boolean; now: string; aiLive: boolean; aiProvider: "claude" | "openai" | "mock" }>(
      "GET",
      "/api/health"
    ),
  submitRequest: (text: string) => req<ProjectState>("POST", "/api/requests", { text }),
  decompose: (projectId: string) =>
    req<ProjectState>("POST", `/api/projects/${projectId}/decompose`),
  recommendAll: (projectId: string) =>
    req<ProjectState>("POST", `/api/projects/${projectId}/recommend-all`),
  approve: (taskId: string, memberId?: string) =>
    req<ProjectState>("POST", `/api/tasks/${taskId}/approve`, { memberId }),
  reject: (taskId: string) => req<ProjectState>("POST", `/api/tasks/${taskId}/reject`),
  progress: (taskId: string, note?: string) =>
    req<ProjectState>("POST", `/api/tasks/${taskId}/progress`, { note, source: "manual" }),
  complete: (taskId: string) => req<ProjectState>("POST", `/api/tasks/${taskId}/complete`),
  advanceClock: (hours: number) =>
    req<{ now: string; newAlerts: DelayAlert[] }>("POST", "/api/simulate/advance", { hours }),
  ackAlert: (alertId: string) => req<DelayAlert>("POST", `/api/alerts/${alertId}/ack`),
  resolveAlert: (alertId: string) => req<DelayAlert>("POST", `/api/alerts/${alertId}/resolve`),
  submitMeeting: (projectId: string, text: string) =>
    req<{ note: MeetingNote; newTasks: Task[] } & ProjectState>("POST", "/api/meetings", {
      projectId,
      text,
    }),
  getProject: (projectId: string) => req<ProjectState>("GET", `/api/projects/${projectId}`),
  continueProject: (projectId: string, text: string) =>
    req<ProjectState>("POST", `/api/projects/${projectId}/continue`, { text }),
};
