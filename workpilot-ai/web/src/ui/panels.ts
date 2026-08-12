import type { Member, MeetingNote, ProjectState, Task } from "../types.js";
import { escapeHtml, fmtTime, statusClass, statusLabel } from "./format.js";

function memberName(members: Member[], id?: string): string {
  if (!id) return "-";
  return members.find((m) => m.id === id)?.name ?? id;
}

/** 작업이 하나라도 있고 전부 done이면 "완료" — 그 전에는 계속 자동으로 뭔가 진행 중이라는 뜻. */
function isAllDone(state: ProjectState): boolean {
  return state.tasks.length > 0 && state.tasks.every((t) => t.status === "done");
}

function autopilotBadge(state: ProjectState): string {
  return isAllDone(state)
    ? `<span class="badge badge--done">✓ 완료</span>`
    : `<span class="badge badge--auto">자동 진행 중</span>`;
}

export function renderRequestPanel(state: ProjectState | null): string {
  if (!state) {
    return `
      <div class="card">
        <h2>1. 업무 요청</h2>
        <p class="muted">PM이 자연어로 업무를 지시하면 AI가 분석합니다. (예: "회원가입 시스템을 만들고 테스트까지 진행해줘")</p>
        <textarea id="request-text" rows="3" placeholder="무엇을 만들까요?"></textarea>
        <button data-action="submit-request" class="btn btn--primary">요청 분석</button>
      </div>`;
  }
  const a = state.project.analysis;
  return `
    <div class="card">
      <h2>1. 업무 요청</h2>
      <p><strong>${escapeHtml(state.project.name)}</strong></p>
      <p class="muted" style="white-space: pre-line;">"${escapeHtml(state.project.requestText)}"</p>
      ${
        a
          ? `<div class="analysis">
              <div><span class="tag tag--ok">포함</span> ${a.included.map(escapeHtml).join(", ") || "-"}</div>
              <div><span class="tag tag--warn">확인 필요</span> ${a.uncertain.map(escapeHtml).join(", ") || "-"}</div>
            </div>`
          : ""
      }
      ${renderNextStepsSection(state)}
      <button data-action="new-request" class="btn btn--ghost">다른 프로젝트 요청</button>
    </div>`;
}

function renderNextStepsSection(state: ProjectState): string {
  if (!isAllDone(state)) return "";
  const suggestions = state.project.nextStepSuggestions;
  return `
    <div class="next-steps">
      <h3>다음 단계 <span class="badge badge--auto">AI 추천</span></h3>
      ${
        suggestions === undefined
          ? `<p class="muted">⏳ AI가 다음 단계를 추천하는 중...</p>`
          : suggestions.length === 0
          ? `<p class="muted">추천할 다음 단계가 마땅치 않습니다. 아래에 직접 입력해서 이어가세요.</p>`
          : `<div class="suggestion-list">
              ${suggestions
                .map(
                  (s) =>
                    `<button data-action="continue-suggestion" data-text="${escapeHtml(s)}" class="btn btn--suggestion">${escapeHtml(s)}</button>`
                )
                .join("")}
            </div>`
      }
      <textarea id="continue-text" rows="2" placeholder="또는 직접 다음 지시를 입력하세요 (예: 비밀번호 재설정 기능 추가해줘)"></textarea>
      <button data-action="continue-custom" class="btn btn--primary">이 내용으로 계속 진행</button>
    </div>`;
}

export function renderPipelinePanel(state: ProjectState): string {
  const hasTasks = state.tasks.length > 0;
  const hasPending = state.tasks.some((t) => t.status === "pending");
  const allDone = isAllDone(state);
  return `
    <div class="card">
      <h2>3. 파이프라인 ${autopilotBadge(state)}</h2>
      <p class="muted">
        ${
          allDone
            ? "모든 작업이 완료됐습니다 — 오토파일럿이 더 이상 할 일이 없습니다."
            : "분해 → 추천 → 배정까지 AI가 자동으로 이어서 처리합니다. 아래 버튼은 수동 재실행용입니다."
        }
      </p>
      <div class="pipeline-actions">
        <button data-action="decompose" class="btn btn--ghost" ${hasTasks ? "disabled" : ""}>작업 분해 (WBS)</button>
        <button data-action="recommend-all" class="btn btn--ghost" ${!hasPending ? "disabled" : ""}>담당자 추천 받기</button>
      </div>
    </div>`;
}

function ganttBounds(tasks: Task[]): { min: number; max: number } | null {
  const starts = tasks.map((t) => t.plannedStart).filter(Boolean).map((s) => new Date(s!).getTime());
  const ends = tasks.map((t) => t.plannedEnd).filter(Boolean).map((s) => new Date(s!).getTime());
  if (starts.length === 0 || ends.length === 0) return null;
  const min = Math.min(...starts);
  const max = Math.max(...ends);
  if (!(max > min)) return null;
  return { min, max };
}

function renderGanttBar(t: Task, bounds: { min: number; max: number } | null, nowIso: string): string {
  if (!bounds || !t.plannedStart || !t.plannedEnd) return "";
  const span = bounds.max - bounds.min;
  const start = new Date(t.plannedStart).getTime();
  const end = new Date(t.plannedEnd).getTime();
  const left = Math.max(0, ((start - bounds.min) / span) * 100);
  const width = Math.max(1.5, ((end - start) / span) * 100);
  const now = new Date(nowIso).getTime();
  const nowLeft = Math.min(100, Math.max(0, ((now - bounds.min) / span) * 100));
  const showNow = now >= bounds.min && now <= bounds.max && t.status !== "done" && t.status !== "pending";
  return `
    <div class="gantt-track">
      <div class="gantt-bar gantt-bar--${t.status}" style="left:${left}%;width:${width}%"></div>
      ${showNow ? `<div class="gantt-now" style="left:${nowLeft}%"></div>` : ""}
    </div>`;
}

export function renderTaskPanel(state: ProjectState): string {
  if (state.tasks.length === 0) {
    return `<div class="card"><h2>4. 작업(WBS)</h2><p class="muted">아직 분해된 작업이 없습니다.</p></div>`;
  }

  const bounds = ganttBounds(state.tasks);
  const rows = state.tasks
    .map((t) => {
      return `<div class="task-row" data-task-row="${t.id}">
        <div class="task-row__head">
          <span class="${statusClass(t.status)}">${statusLabel(t.status)}</span>
          <strong>${escapeHtml(t.title)}</strong>
        </div>
        <div class="task-row__meta muted">
          담당: ${escapeHtml(memberName(state.members, t.assigneeId))}
          · 예상 ${t.estimateHours}h
          · 일정 ${fmtTime(t.plannedStart)} → ${fmtTime(t.plannedEnd)}
          ${t.dependsOn.length ? `· 선행 ${t.dependsOn.length}건` : ""}
        </div>
        ${renderGanttBar(t, bounds, state.now)}
        ${renderDeliverable(t)}
        ${renderTaskActions(t, state.members)}
      </div>`;
    })
    .join("");

  return `<div class="card"><h2>4. 작업(WBS)</h2><div class="task-list">${rows}</div></div>`;
}

function renderDeliverable(t: Task): string {
  if (t.deliverable) {
    return `<div class="deliverable">
      <span class="tag tag--ok">결과물</span>
      ${deliverableLinkButton(t, t.deliverable.filename)}
      ${webViewLink(t)}
      ${t.deliverable.language ? `<span class="muted">(${escapeHtml(t.deliverable.language)})</span>` : ""}
    </div>`;
  }
  if (t.status === "active") {
    return `<div class="deliverable muted">⏳ AI가 결과물을 생성하는 중...</div>`;
  }
  return "";
}

function isHtmlDeliverable(t: Task): boolean {
  const filename = t.deliverable?.filename ?? "";
  const language = t.deliverable?.language ?? "";
  return /\.html?$/i.test(filename) || /^html$/i.test(language);
}

function deliverableFileUrl(t: Task): string {
  return `/files/${t.projectId}/${encodeURIComponent(t.deliverable!.filename)}`;
}

/** 결과물 파일을 클릭하면 새 탭이 아니라 앱 안 모달로 바로 열리는 버튼(웹에서 바로 보기). */
function deliverableLinkButton(t: Task, label: string): string {
  const url = deliverableFileUrl(t);
  return `<button
      type="button"
      data-action="view-deliverable"
      data-url="${url}"
      data-title="${escapeHtml(t.title)}"
      data-language="${escapeHtml(t.deliverable!.language ?? "")}"
      class="deliverable-link"
    >${escapeHtml(label)}</button>`;
}

/** HTML 결과물만 — 모달을 거치지 않고 새 탭에서 바로 실제 구동 화면을 여는 링크.
 * 클릭 한 번으로 바로 열리는 게 목적이라 <a target="_blank">로 브라우저 기본 동작을 그대로 쓴다. */
function webViewLink(t: Task): string {
  if (!isHtmlDeliverable(t)) return "";
  const url = deliverableFileUrl(t);
  return `<a
      href="${url}"
      target="_blank"
      rel="noopener"
      class="deliverable-link deliverable-link--web"
    >🌐 웹으로 보기</a>`;
}

function renderTaskActions(t: Task, members: Member[]): string {
  if (t.status === "waiting_approval") {
    const top = t.recommendation?.[0];
    const options = members
      .filter((m) => !m.isLead)
      .map(
        (m) =>
          `<option value="${m.id}" ${m.id === top?.memberId ? "selected" : ""}>${escapeHtml(m.name)}</option>`
      )
      .join("");
    return `
      <div class="task-row__reco">
        ${
          top
            ? `<span class="muted">AI 추천: <strong>${escapeHtml(
                memberName(members, top.memberId)
              )}</strong> (score ${top.score}) — ${escapeHtml(top.reason)}</span>`
            : ""
        }
      </div>
      <div class="task-row__actions">
        <select id="assignee-select-${t.id}" data-select-member data-task="${t.id}">${options}</select>
        <button data-action="approve" data-task="${t.id}" class="btn btn--primary">승인/배정</button>
        <button data-action="reject" data-task="${t.id}" class="btn btn--ghost">거절</button>
      </div>`;
  }
  if (t.status === "assigned") {
    return `<div class="task-row__actions">
      <button data-action="progress" data-task="${t.id}" class="btn">진행 신호 보내기</button>
    </div>`;
  }
  if (t.status === "active" || t.status === "delayed") {
    return `<div class="task-row__actions">
      <button data-action="progress" data-task="${t.id}" class="btn">진행 신호 추가</button>
      <button data-action="complete" data-task="${t.id}" class="btn btn--primary">완료 처리</button>
    </div>`;
  }
  return "";
}

export function renderAlertPanel(state: ProjectState): string {
  const open = state.alerts.filter((a) => a.status !== "resolved");
  if (open.length === 0) {
    return `<div class="card"><h2>5. 지연 알림</h2><p class="muted">현재 열린 지연 알림이 없습니다.</p></div>`;
  }
  const rows = open
    .map((a) => {
      const task = state.tasks.find((t) => t.id === a.taskId);
      return `<div class="alert-row alert-row--${a.status}">
        <div><strong>${escapeHtml(task?.title ?? a.taskId)}</strong></div>
        <div class="muted">${escapeHtml(a.message)}</div>
        <div class="muted">제안: ${escapeHtml(a.proposedAction)}</div>
        <div class="task-row__actions">
          ${
            a.status === "open"
              ? `<button data-action="ack-alert" data-alert="${a.id}" class="btn btn--ghost">확인</button>`
              : ""
          }
          <button data-action="resolve-alert" data-alert="${a.id}" class="btn">해결됨</button>
        </div>
      </div>`;
    })
    .join("");
  return `<div class="card"><h2>5. 지연 알림</h2>${rows}</div>`;
}

/** 카카오톡 채팅 요약 카드처럼: 상단 TL;DR 한 줄 + 참여자 칩 + 주제별 요약, 그 아래 상세(결정/액션/리스크)는 접어둔다. */
function renderMeetingNote(n: MeetingNote): string {
  const participants = n.participants.length
    ? `<div class="meeting-participants">${n.participants.map((p) => `<span class="chip">${escapeHtml(p)}</span>`).join("")}</div>`
    : "";
  const topics = n.topics.length
    ? `<div class="meeting-topics">
        ${n.topics
          .map(
            (t) =>
              `<div class="meeting-topic"><span class="meeting-topic__label">${escapeHtml(t.topic)}</span> <span class="muted">${escapeHtml(t.summary)}</span></div>`
          )
          .join("")}
      </div>`
    : "";
  return `<div class="meeting-note">
    <div class="meeting-note__head">
      <span class="muted">${fmtTime(n.date)}</span>
      ${participants}
    </div>
    ${n.tldr ? `<div class="meeting-tldr">💬 ${escapeHtml(n.tldr)}</div>` : ""}
    ${topics}
    <details class="meeting-detail">
      <summary>결정·액션·리스크 상세</summary>
      <div><span class="tag tag--ok">결정</span> ${n.decisions.map(escapeHtml).join(" / ") || "-"}</div>
      <div><span class="tag tag--warn">액션</span> ${n.actionItems.map(escapeHtml).join(" / ") || "-"}</div>
      <div><span class="tag tag--danger">리스크</span> ${n.risks.map(escapeHtml).join(" / ") || "-"}</div>
    </details>
    <button type="button" data-action="download-meeting-pdf" data-note="${n.id}" class="btn btn--ghost meeting-note__download">📄 PDF 다운로드</button>
  </div>`;
}

// 업무 요청과는 별개인 진입점이라 프로젝트가 아직 없어도(state === null) 항상 렌더링해서
// 앱을 켜자마자 회의 내용을 바로 붙여넣을 수 있게 한다 — 최초 제출 시 서버가 프로젝트를 만든다.
export function renderMeetingPanel(state: ProjectState | null): string {
  const notes = state
    ? state.meetingNotes
        .slice()
        .reverse()
        .map(renderMeetingNote)
        .join("")
    : "";
  return `
    <div class="card">
      <h2>2. 회의 요약</h2>
      <p class="muted">회의 메모나 "이름: 발언" 형식의 채팅 로그를 그대로 붙여넣어도 참여자/주제를 인식합니다.</p>
      <textarea id="meeting-text" rows="4" placeholder="예)
지연: API 명세 이번 주까지 확정하기로 했어요
민수: 결제 연동은 다음 스프린트로 미루죠
지연: 결제사 응답 지연이 리스크로 걱정되네요"></textarea>
      <div class="meeting-attach">
        <label for="meeting-files" class="btn btn--ghost">📎 파일 첨부</label>
        <!-- 실제 <input type="file">은 main.ts가 딱 한 번 만들어서 여기(mount point)로 옮겨 붙인다.
             2초 폴링마다 이 패널 전체가 innerHTML로 다시 그려지는데, 그때마다 input을 새로 만들면
             OS 파일 선택창이 떠 있는 동안 그 창이 참조하던 input이 DOM에서 떨어져나가 change 이벤트가
             씹히는 문제가 있었다 — 항상 같은 input 인스턴스를 재사용해서 이 문제를 없앤다. -->
        <span id="meeting-files-mount"></span>
        <span class="muted">문서(txt/md/pdf/docx)나 음성 파일을 첨부하면 내용을 읽거나 전사해서 함께 요약합니다. (파일당 25MB 이하)</span>
      </div>
      <div id="meeting-file-list" class="meeting-file-list"></div>
      <button data-action="submit-meeting" class="btn">요약 반영</button>
      ${notes}
    </div>`;
}

export function renderSimPanel(state: ProjectState): string {
  const allDone = isAllDone(state);
  return `
    <div class="card card--sim">
      <h2>가상 시계 ${autopilotBadge(state)}</h2>
      <p class="muted">
        현재 가상 시각: <strong>${fmtTime(state.now)}</strong> —
        ${
          allDone
            ? "모든 작업이 완료돼 시계가 더 이상 진행할 게 없습니다."
            : "오토파일럿이 실제 개발팀처럼 착수/진행/완료를 자동으로 흘려보내고 있습니다. 더 빨리 보고 싶다면 아래로 강제 전진할 수 있습니다."
        }
      </p>
      <div class="task-row__actions">
        <button data-action="advance" data-hours="24" class="btn btn--ghost" ${allDone ? "disabled" : ""}>+1일 빨리감기</button>
        <button data-action="advance" data-hours="72" class="btn btn--ghost" ${allDone ? "disabled" : ""}>+3일 빨리감기</button>
        <button data-action="advance" data-hours="240" class="btn btn--ghost" ${allDone ? "disabled" : ""}>+10일 빨리감기</button>
      </div>
    </div>`;
}

export function renderDeliverablesPanel(state: ProjectState): string {
  const withDeliverable = state.tasks.filter((t) => t.deliverable);
  if (withDeliverable.length === 0) {
    return `
      <div class="card">
        <h2>6. 결과물</h2>
        <p class="muted">아직 생성된 결과물이 없습니다. 작업이 착수(진행중)되면 AI가 자동으로 파일을 만들어 여기에 모아 보여줍니다.</p>
      </div>`;
  }
  const rows = withDeliverable
    .map((t) => {
      return `<div class="deliverable-row">
        <div>
          <span class="${statusClass(t.status)}">${statusLabel(t.status)}</span>
          ${deliverableLinkButton(t, t.title)}
          ${webViewLink(t)}
          <span class="muted">${escapeHtml(t.deliverable!.filename)}${
        t.deliverable!.language ? ` · ${escapeHtml(t.deliverable!.language)}` : ""
      }</span>
        </div>
        ${t.deliverable!.summary ? `<div class="deliverable-row__summary muted">${escapeHtml(t.deliverable!.summary)}</div>` : ""}
      </div>`;
    })
    .join("");
  return `
    <div class="card">
      <h2>6. 결과물 (${withDeliverable.length}건)</h2>
      <p class="muted">작업별로 AI가 실제로 생성한 파일입니다. 눌러서 바로 확인할 수 있습니다.</p>
      <div class="deliverable-list">${rows}</div>
    </div>`;
}
