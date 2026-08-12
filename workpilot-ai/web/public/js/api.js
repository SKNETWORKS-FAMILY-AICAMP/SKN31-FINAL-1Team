// ── REST API 클라이언트 (같은 오리진에서 서빙되므로 base는 빈 문자열) ──
async function req(method, path, body) {
    const res = await fetch(path, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error ?? `HTTP ${res.status}`);
    }
    return res.json();
}
export const api = {
    health: () => req("GET", "/api/health"),
    submitRequest: (text) => req("POST", "/api/requests", { text }),
    decompose: (projectId) => req("POST", `/api/projects/${projectId}/decompose`),
    recommendAll: (projectId) => req("POST", `/api/projects/${projectId}/recommend-all`),
    approve: (taskId, memberId) => req("POST", `/api/tasks/${taskId}/approve`, { memberId }),
    reject: (taskId) => req("POST", `/api/tasks/${taskId}/reject`),
    progress: (taskId, note) => req("POST", `/api/tasks/${taskId}/progress`, { note, source: "manual" }),
    complete: (taskId) => req("POST", `/api/tasks/${taskId}/complete`),
    advanceClock: (hours) => req("POST", "/api/simulate/advance", { hours }),
    ackAlert: (alertId) => req("POST", `/api/alerts/${alertId}/ack`),
    resolveAlert: (alertId) => req("POST", `/api/alerts/${alertId}/resolve`),
    submitMeeting: (projectId, text) => req("POST", "/api/meetings", {
        projectId,
        text,
    }),
    getProject: (projectId) => req("GET", `/api/projects/${projectId}`),
    continueProject: (projectId, text) => req("POST", `/api/projects/${projectId}/continue`, { text }),
};
