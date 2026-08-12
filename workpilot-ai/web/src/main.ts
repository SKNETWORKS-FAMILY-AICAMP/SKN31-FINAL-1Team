import { api } from "./api.js";
import { OfficeCanvas } from "./office/canvas.js";
import {
  renderAlertPanel,
  renderDeliverablesPanel,
  renderMeetingPanel,
  renderPipelinePanel,
  renderRequestPanel,
  renderSimPanel,
  renderTaskPanel,
} from "./ui/panels.js";
import { escapeHtml, fmtTime } from "./ui/format.js";
import type { MeetingAttachmentPayload, MeetingNote, ProjectState } from "./types.js";

const requestPanelEl = document.getElementById("request-panel")!;
const pipelinePanelEl = document.getElementById("pipeline-panel")!;
const taskPanelEl = document.getElementById("task-panel")!;
const alertPanelEl = document.getElementById("alert-panel")!;
const meetingPanelEl = document.getElementById("meeting-panel")!;
const deliverablesPanelEl = document.getElementById("deliverables-panel")!;
const simPanelEl = document.getElementById("sim-panel")!;
const officeCanvasEl = document.getElementById("office-canvas") as HTMLCanvasElement;
const toastEl = document.getElementById("toast")!;
const aiModeBadgeEl = document.getElementById("ai-mode-badge")!;
const clockDisplayEl = document.getElementById("clock-display")!;
const modalEl = document.getElementById("deliverable-modal")!;
const modalTitleEl = document.getElementById("modal-title")!;
const modalSubtitleEl = document.getElementById("modal-subtitle")!;
const modalContentEl = document.getElementById("modal-content")!;
const modalRawLinkEl = document.getElementById("modal-raw-link") as HTMLAnchorElement;
const modalTabsEl = document.getElementById("modal-tabs")!;
const modalTabPreviewEl = document.getElementById("modal-tab-preview")!;
const modalTabCodeEl = document.getElementById("modal-tab-code")!;
const modalPreviewEl = document.getElementById("modal-preview") as HTMLIFrameElement;

api
  .health()
  .then((h) => {
    const providerLabel = h.aiProvider === "openai" ? "OpenAI" : h.aiProvider === "claude" ? "Claude" : "Mock";
    aiModeBadgeEl.textContent = h.aiLive ? `● ${providerLabel} API 연동됨` : `○ ${providerLabel}(rule-based) 모드`;
    aiModeBadgeEl.className = `badge ${h.aiLive ? "badge--live" : "badge--mock"}`;
  })
  .catch(() => {
    aiModeBadgeEl.textContent = "서버 연결 확인 필요";
    aiModeBadgeEl.className = "badge badge--mock";
  });

const office = new OfficeCanvas(officeCanvasEl);
office.start();

let currentState: ProjectState | null = null;
let pollTimer: number | undefined;

function toast(msg: string) {
  toastEl.textContent = msg;
  toastEl.classList.add("toast--show");
  window.setTimeout(() => toastEl.classList.remove("toast--show"), 2500);
}

// ── 회의 요약 첨부파일 ────────────────────────────────────────────────
// 프로젝트 상태와 무관한 순수 클라이언트 임시 상태라 ProjectState에는 두지 않는다.
// #meeting-panel은 renderAll()마다 innerHTML로 통째로 교체되므로(2초 폴링 포함), 그 안의
// 목록 div도 매번 새 노드로 바뀐다 — 그래서 목록은 이 배열을 기준으로 매 렌더링 직후 다시
// 그려 넣는다(withPreservedInputs가 챙겨주는 텍스트 입력값과 달리 파일은 그렇게 복원할 수
// 없기 때문).
let pendingMeetingFiles: File[] = [];

// <input type="file">은 renderMeetingPanel()이 만드는 HTML 문자열에 포함시키지 않고, 여기서
// 딱 한 번만 만들어서 매 렌더링 후 #meeting-files-mount로 옮겨 붙인다(mountMeetingFilesInput).
// 예전엔 패널 HTML 안에 <input>을 직접 넣었는데, OS 파일 선택창이 열려 있는 동안(사용자가
// 폴더를 탐색하느라 몇 초 이상 걸리는 경우가 흔하다) 2초 폴링이 끼어들어 innerHTML을 통째로
// 갈아치우면 선택창이 참조하던 input이 DOM에서 떨어져나갔다 — 그 상태에서 파일을 골라도
// change 이벤트가 document로 버블링되지 않아 "파일을 선택했는데 아무 반응이 없는" 버그가
// 있었다. 항상 같은 input 인스턴스를 유지하고 직접 리스너를 붙여두면, 그 인스턴스가 어느
// 순간 잠깐 DOM 밖에 있었더라도(재부착 전) change 이벤트는 그대로 잡힌다.
const meetingFilesInputEl = document.createElement("input");
meetingFilesInputEl.type = "file";
meetingFilesInputEl.id = "meeting-files";
meetingFilesInputEl.className = "visually-hidden";
meetingFilesInputEl.multiple = true;
meetingFilesInputEl.accept = ".txt,.md,.markdown,.log,.csv,.pdf,.docx,audio/*";
// 서버(meetingAttachments.ts)도 같은 25MB 상한을 두지만, 여기서 먼저 걸러야 사용자가 선택
// 즉시 이유를 알 수 있고 base64 인코딩 + 업로드를 헛수고로 만들지 않는다.
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024; // 25MB

meetingFilesInputEl.addEventListener("change", () => {
  const rejected: string[] = [];
  for (const f of Array.from(meetingFilesInputEl.files ?? [])) {
    if (f.size > MAX_ATTACHMENT_BYTES) {
      rejected.push(`${f.name} (${formatFileSize(f.size)})`);
      continue;
    }
    const dup = pendingMeetingFiles.some(
      (existing) => existing.name === f.name && existing.size === f.size && existing.lastModified === f.lastModified
    );
    if (!dup) pendingMeetingFiles.push(f);
  }
  meetingFilesInputEl.value = ""; // 같은 파일을 다시 선택할 수 있도록 초기화
  syncMeetingFileList();
  if (rejected.length > 0) {
    toast(`25MB를 초과해 첨부할 수 없습니다: ${rejected.join(", ")}`);
  }
});

function mountMeetingFilesInput() {
  const mount = document.getElementById("meeting-files-mount");
  if (mount && meetingFilesInputEl.parentElement !== mount) {
    mount.appendChild(meetingFilesInputEl);
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function syncMeetingFileList() {
  const listEl = document.getElementById("meeting-file-list");
  if (!listEl) return;
  listEl.innerHTML = pendingMeetingFiles
    .map(
      (f, i) =>
        `<span class="chip chip--file">📎 ${escapeHtml(f.name)} <span class="muted">(${formatFileSize(f.size)})</span> <button type="button" data-action="remove-meeting-file" data-index="${i}" class="chip__remove" aria-label="첨부 제거">✕</button></span>`
    )
    .join("");
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error(`${file.name}을(를) 읽지 못했습니다.`));
    reader.readAsDataURL(file);
  });
}

async function buildAttachmentPayloads(files: File[]): Promise<MeetingAttachmentPayload[]> {
  return Promise.all(
    files.map(async (f) => ({
      name: f.name,
      mimeType: f.type || "",
      dataBase64: await readFileAsDataUrl(f),
    }))
  );
}

// ── 회의 요약 PDF 다운로드 ────────────────────────────────────────────
// 서버에 PDF 생성 라이브러리(+ 한글 폰트 임베딩)를 새로 추가하는 대신, 브라우저 자체의
// "인쇄 → PDF로 저장"을 그대로 활용한다 — 별도 의존성 없이 화면에 보이는 한글이 그대로
// PDF에 반영되고, 사용자가 저장 위치/파일명을 직접 고를 수 있다는 것도 일반적인 파일
// 다운로드와 동일하다.
function buildMeetingNotePrintHtml(note: MeetingNote, projectName: string): string {
  const listHtml = (items: string[]) =>
    items.length ? `<ul>${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : "<p class=\"empty\">-</p>";
  const topicsHtml = note.topics.length
    ? `<ul>${note.topics
        .map((t) => `<li><strong>${escapeHtml(t.topic)}</strong> — ${escapeHtml(t.summary)}</li>`)
        .join("")}</ul>`
    : "<p class=\"empty\">-</p>";
  const participantsHtml = note.participants.length
    ? `<div class="chips">${note.participants.map((p) => `<span>${escapeHtml(p)}</span>`).join("")}</div>`
    : "";
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>회의 요약 - ${escapeHtml(projectName)}</title>
<style>
  body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; color: #111; padding: 32px; max-width: 720px; margin: 0 auto; line-height: 1.6; }
  h1 { font-size: 20px; margin: 0 0 2px; }
  .meta { color: #666; font-size: 12px; margin-bottom: 18px; }
  .tldr { background: #f2f2f6; border-left: 4px solid #333; padding: 12px 16px; margin-bottom: 18px; font-size: 14px; }
  h2 { font-size: 14px; margin: 18px 0 6px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
  ul { margin: 0; padding-left: 20px; }
  li { margin-bottom: 4px; font-size: 13px; }
  p.empty { color: #999; font-size: 13px; margin: 0; }
  .chips span { display: inline-block; border: 1px solid #999; border-radius: 3px; padding: 2px 8px; margin: 0 6px 6px 0; font-size: 12px; }
  .raw { white-space: pre-wrap; font-size: 12px; color: #444; background: #fafafa; border: 1px solid #ddd; padding: 12px; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
  <h1>회의 요약</h1>
  <div class="meta">${escapeHtml(projectName)} · ${fmtTime(note.date)}</div>
  ${note.tldr ? `<div class="tldr">💬 ${escapeHtml(note.tldr)}</div>` : ""}
  ${participantsHtml ? `<h2>참여자</h2>${participantsHtml}` : ""}
  <h2>주제별 요약</h2>
  ${topicsHtml}
  <h2>결정 사항</h2>
  ${listHtml(note.decisions)}
  <h2>액션 아이템</h2>
  ${listHtml(note.actionItems)}
  <h2>리스크</h2>
  ${listHtml(note.risks)}
  <h2>원문</h2>
  <div class="raw">${escapeHtml(note.rawText)}</div>
</body>
</html>`;
}

// innerHTML로 패널을 다시 그리면 그 안의 <textarea>/<select>도 통째로 새 노드로
// 교체된다. 2초 폴링마다 renderAll()이 호출되므로, 사용자가 회의록을 붙여넣거나
// 담당자를 고르는 도중에 poll이 끼어들면 입력값이 사라져 보이는 문제가 있었다.
// 재렌더링 전후로 값/커서/포커스를 스냅샷-복원해서 막는다.
function withPreservedInputs<T>(fn: () => T): T {
  const editable = Array.from(
    document.querySelectorAll<HTMLTextAreaElement | HTMLInputElement | HTMLSelectElement>(
      "#panel textarea[id], #panel input[id], #panel select[id]"
    )
  );
  const snapshots = editable.map((el) => ({
    id: el.id,
    value: el.value,
    selStart: "selectionStart" in el ? (el as HTMLTextAreaElement).selectionStart : null,
    selEnd: "selectionEnd" in el ? (el as HTMLTextAreaElement).selectionEnd : null,
    focused: document.activeElement === el,
  }));

  const result = fn();

  for (const snap of snapshots) {
    const el = document.getElementById(snap.id) as
      | HTMLTextAreaElement
      | HTMLInputElement
      | HTMLSelectElement
      | null;
    if (!el) continue;
    el.value = snap.value;
    if (snap.focused) {
      el.focus();
      if ("setSelectionRange" in el && snap.selStart !== null) {
        try {
          (el as HTMLTextAreaElement).setSelectionRange(snap.selStart, snap.selEnd ?? snap.selStart);
        } catch {
          /* 일부 input type은 selection 범위를 지원하지 않음 — 무시해도 무방 */
        }
      }
    }
  }
  return result;
}

function renderAll() {
  withPreservedInputs(() => {
    requestPanelEl.innerHTML = renderRequestPanel(currentState);
    // 회의 요약은 업무 요청과 별개인 진입점이라 프로젝트가 없어도 항상 보여준다.
    meetingPanelEl.innerHTML = renderMeetingPanel(currentState);
    mountMeetingFilesInput(); // 유일한 <input type="file"> 인스턴스를 새로 그려진 mount point로 재부착
    syncMeetingFileList(); // innerHTML 교체로 방금 비워진 첨부 목록을 pendingMeetingFiles 기준으로 다시 채운다.
    if (currentState) {
      // 업무 요청 없이 회의로만 시작한 프로젝트(requestText === "")는 파이프라인/WBS/
      // 지연알림/결과물이 보여줄 실질적인 내용이 없어(회의 액션 아이템만 있는 상태) 굳이
      // 노출하지 않는다 — 업무 요청을 실제로 넣은 프로젝트에서는 그대로 다 보여준다.
      const hasRealRequest = currentState.project.requestText.trim() !== "";
      if (hasRealRequest) {
        pipelinePanelEl.innerHTML = renderPipelinePanel(currentState);
        taskPanelEl.innerHTML = renderTaskPanel(currentState);
        alertPanelEl.innerHTML = renderAlertPanel(currentState);
        deliverablesPanelEl.innerHTML = renderDeliverablesPanel(currentState);
      } else {
        pipelinePanelEl.innerHTML = "";
        taskPanelEl.innerHTML = "";
        alertPanelEl.innerHTML = "";
        deliverablesPanelEl.innerHTML = "";
      }
      simPanelEl.innerHTML = renderSimPanel(currentState);
      office.setState(currentState.members, currentState.tasks);
      clockDisplayEl.textContent = `⏱ ${fmtTime(currentState.now)}`;
    } else {
      pipelinePanelEl.innerHTML = "";
      taskPanelEl.innerHTML = "";
      alertPanelEl.innerHTML = "";
      deliverablesPanelEl.innerHTML = "";
      simPanelEl.innerHTML = "";
      office.setState([], []);
      clockDisplayEl.textContent = "";
    }
  });
}

function setState(s: ProjectState) {
  currentState = s;
  renderAll();
}

function startPolling(projectId: string) {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = window.setInterval(async () => {
    try {
      const s = await api.getProject(projectId);
      setState(s);
    } catch {
      /* 네트워크 일시 오류는 다음 polling에서 재시도 */
    }
  }, 2000);
}

async function guarded(fn: () => Promise<void>) {
  try {
    await fn();
  } catch (err) {
    toast(err instanceof Error ? err.message : String(err));
  }
}

// ── 결과물 미리보기 모달 ─────────────────────────────────────────────
// /files/... 링크를 새 탭으로 그냥 열면 브라우저 기본 text/plain 뷰라 밋밋하고, 무엇보다
// "코드"만 보여줄 뿐 실제로 동작하는 화면은 아니다. .html 결과물은 iframe에 srcdoc으로
// 그대로 그려서 진짜 눌러볼 수 있는 화면으로 보여주고("미리보기" 탭), 코드도 언제든
// "코드" 탭에서 볼 수 있다. 백엔드/테스트처럼 화면이 없는 파일은 탭 없이 코드만 보여준다.

function isHtmlDeliverable(url: string, language: string): boolean {
  const l = language.toLowerCase();
  return l === "html" || l === "htm" || /\.html?$/i.test(url);
}

type ModalTab = "preview" | "code";

function setModalTab(tab: ModalTab) {
  modalPreviewEl.classList.toggle("hidden", tab !== "preview");
  modalContentEl.classList.toggle("hidden", tab !== "code");
  modalTabPreviewEl.classList.toggle("modal__tab--active", tab === "preview");
  modalTabCodeEl.classList.toggle("modal__tab--active", tab === "code");
}

function closeModal() {
  modalEl.classList.add("hidden");
  modalContentEl.textContent = "";
  modalPreviewEl.srcdoc = "";
}

async function openDeliverableModal(url: string, title: string, language: string) {
  const isHtml = isHtmlDeliverable(url, language);
  modalTitleEl.textContent = title;
  modalSubtitleEl.textContent = language ? `(${language})` : "";
  modalRawLinkEl.href = url;
  modalTabsEl.classList.toggle("hidden", !isHtml);
  modalContentEl.textContent = "불러오는 중...";
  modalPreviewEl.srcdoc = "";
  setModalTab(isHtml ? "preview" : "code");
  modalEl.classList.remove("hidden");
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`파일을 불러오지 못했습니다 (HTTP ${res.status})`);
    const text = await res.text();
    modalContentEl.textContent = text;
    if (isHtml) modalPreviewEl.srcdoc = text;
  } catch (err) {
    modalContentEl.textContent = `불러오기 실패: ${err instanceof Error ? err.message : String(err)}`;
    setModalTab("code");
  }
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !modalEl.classList.contains("hidden")) closeModal();
});

// 버튼 옆에 스피너 + 로딩 텍스트를 표시해 "지금 실제로 API를 호출하고 있다"는 걸 눈으로 확인시켜준다.
// 성공 시에는 보통 setState()가 패널을 통째로 다시 그리면서 버튼 자체가 사라지므로 별 문제 없지만,
// 실패해서 버튼이 그대로 남아있는 경우를 위해 원래 라벨을 복원한다.
function setButtonLoading(btn: HTMLElement, loading: boolean, loadingLabel: string) {
  if (loading) {
    btn.dataset.originalLabel = btn.textContent ?? "";
    (btn as HTMLButtonElement).disabled = true;
    btn.innerHTML = `<span class="spinner" aria-hidden="true"></span>${loadingLabel}`;
  } else {
    (btn as HTMLButtonElement).disabled = false;
    btn.textContent = btn.dataset.originalLabel ?? btn.textContent;
  }
}

document.body.addEventListener("click", (ev) => {
  const target = ev.target as HTMLElement;
  const btn = target.closest<HTMLElement>("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;

  if (action === "view-deliverable") {
    const url = btn.dataset.url ?? "";
    if (!url) return;
    openDeliverableModal(url, btn.dataset.title ?? "결과물", btn.dataset.language ?? "");
    return;
  }

  if (action === "close-modal") {
    closeModal();
    return;
  }

  if (action === "modal-tab") {
    const tab = btn.dataset.tab === "preview" ? "preview" : "code";
    setModalTab(tab);
    return;
  }

  if (action === "modal-copy") {
    navigator.clipboard
      .writeText(modalContentEl.textContent ?? "")
      .then(() => toast("클립보드에 복사했습니다."))
      .catch(() => toast("복사에 실패했습니다."));
    return;
  }

  if (action === "remove-meeting-file") {
    const idx = Number(btn.dataset.index);
    pendingMeetingFiles.splice(idx, 1);
    syncMeetingFileList();
    return;
  }

  if (action === "download-meeting-pdf") {
    const note = currentState?.meetingNotes.find((n) => n.id === btn.dataset.note);
    if (!note) return toast("요약 데이터를 찾을 수 없습니다.");
    const printWindow = window.open("", "_blank", "width=800,height=1000");
    if (!printWindow) return toast("팝업이 차단되었습니다 — 브라우저에서 이 사이트의 팝업을 허용해주세요.");
    printWindow.document.open();
    printWindow.document.write(buildMeetingNotePrintHtml(note, currentState?.project.name ?? ""));
    printWindow.document.close();
    // onload 이후에 인쇄 대화상자를 띄워야 내용이 다 그려진 상태에서 열린다.
    printWindow.onload = () => {
      printWindow.focus();
      printWindow.print();
    };
    return;
  }

  if (action === "submit-request") {
    const ta = document.getElementById("request-text") as HTMLTextAreaElement | null;
    const text = ta?.value.trim();
    if (!text) return toast("요청 내용을 입력하세요.");
    setButtonLoading(btn, true, " AI 분석 중...");
    guarded(async () => {
      try {
        const s = await api.submitRequest(text);
        setState(s);
        startPolling(s.project.id);
        toast("요청을 분석했습니다.");
      } finally {
        setButtonLoading(btn, false, "");
      }
    });
    return;
  }

  if (action === "continue-suggestion" || action === "continue-custom") {
    if (!currentState) return;
    const projectId = currentState.project.id;
    const text =
      action === "continue-suggestion"
        ? (btn.dataset.text ?? "")
        : ((document.getElementById("continue-text") as HTMLTextAreaElement | null)?.value.trim() ?? "");
    if (!text) return toast("다음 지시 내용을 입력하세요.");
    setButtonLoading(btn, true, " AI 진행 중...");
    guarded(async () => {
      try {
        const s = await api.continueProject(projectId, text);
        setState(s);
        toast("다음 작업을 시작했습니다.");
      } finally {
        setButtonLoading(btn, false, "");
      }
    });
    return;
  }

  if (action === "new-request") {
    if (pollTimer) window.clearInterval(pollTimer);
    currentState = null;
    renderAll();
    return;
  }

  if (action === "submit-meeting") {
    const ta = document.getElementById("meeting-text") as HTMLTextAreaElement | null;
    const text = ta?.value.trim() ?? "";
    const files = pendingMeetingFiles.slice();
    if (!text && files.length === 0) return toast("회의 내용을 입력하거나 파일을 첨부하세요.");
    const existingProjectId = currentState?.project.id;
    setButtonLoading(btn, true, files.length ? " 파일 처리 중..." : " 요약 중...");
    guarded(async () => {
      try {
        const attachments = await buildAttachmentPayloads(files);
        const result = await api.submitMeeting(existingProjectId, text, attachments);
        setState(result);
        if (!existingProjectId) startPolling(result.project.id); // 회의로 새 프로젝트가 만들어진 경우
        toast(`회의 요약 완료 — 액션 아이템 ${result.newTasks.length}건이 신규 작업으로 생성됨.`);
        if (ta) ta.value = "";
        pendingMeetingFiles = [];
        syncMeetingFileList();
      } finally {
        setButtonLoading(btn, false, "");
      }
    });
    return;
  }

  if (!currentState) return;
  const projectId = currentState.project.id;

  if (action === "decompose") {
    guarded(async () => {
      setState(await api.decompose(projectId));
      toast("작업을 분해했습니다.");
    });
  } else if (action === "recommend-all") {
    guarded(async () => {
      setState(await api.recommendAll(projectId));
      toast("담당자 추천안을 생성했습니다. 승인이 필요합니다.");
    });
  } else if (action === "approve") {
    const taskId = btn.dataset.task!;
    const row = btn.closest<HTMLElement>("[data-task-row]");
    const select = row?.querySelector<HTMLSelectElement>("[data-select-member]");
    guarded(async () => {
      setState(await api.approve(taskId, select?.value));
      toast("배정을 승인했습니다.");
    });
  } else if (action === "reject") {
    guarded(async () => {
      setState(await api.reject(btn.dataset.task!));
      toast("배정을 거절했습니다.");
    });
  } else if (action === "progress") {
    guarded(async () => {
      setState(await api.progress(btn.dataset.task!, "진행 상황 업데이트"));
      toast("진행 신호를 기록했습니다.");
    });
  } else if (action === "complete") {
    guarded(async () => {
      setState(await api.complete(btn.dataset.task!));
      toast("작업을 완료 처리했습니다.");
    });
  } else if (action === "ack-alert") {
    guarded(async () => {
      await api.ackAlert(btn.dataset.alert!);
      setState(await api.getProject(projectId));
    });
  } else if (action === "resolve-alert") {
    guarded(async () => {
      await api.resolveAlert(btn.dataset.alert!);
      setState(await api.getProject(projectId));
    });
  } else if (action === "advance") {
    const hours = Number(btn.dataset.hours ?? "24");
    guarded(async () => {
      const r = await api.advanceClock(hours);
      setState(await api.getProject(projectId));
      if (r.newAlerts.length > 0) toast(`지연 위험 ${r.newAlerts.length}건 감지됨.`);
      else toast("시간을 진행했습니다. 새 지연 알림은 없습니다.");
    });
  }
});

renderAll();
