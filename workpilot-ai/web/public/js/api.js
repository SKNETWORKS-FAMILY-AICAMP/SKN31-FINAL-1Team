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
    // projectId가 없으면(아직 프로젝트가 없는 초기 상태) 서버가 이 회의를 계기로 프로젝트를
    // 새로 만든다 — 회의 요약은 업무 요청 없이도 바로 쓸 수 있는 독립된 진입점이다.
    // attachments는 문서(txt/md/pdf/docx)나 음성 파일을 base64로 인코딩한 것 — 서버가 내용을
    // 추출/전사해서 text와 합쳐 요약한다.
    submitMeeting: (projectId, text, attachments = []) => req("POST", "/api/meetings", {
        projectId,
        text,
        attachments,
    }),
    getProject: (projectId) => req("GET", `/api/projects/${projectId}`),
    continueProject: (projectId, text) => req("POST", `/api/projects/${projectId}/continue`, { text }),
};
