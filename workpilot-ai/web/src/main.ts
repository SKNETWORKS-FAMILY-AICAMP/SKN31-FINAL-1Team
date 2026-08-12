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
import { fmtTime } from "./ui/format.js";
import type { ProjectState } from "./types.js";

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
    if (currentState) {
      pipelinePanelEl.innerHTML = renderPipelinePanel(currentState);
      taskPanelEl.innerHTML = renderTaskPanel(currentState);
      alertPanelEl.innerHTML = renderAlertPanel(currentState);
      meetingPanelEl.innerHTML = renderMeetingPanel(currentState);
      deliverablesPanelEl.innerHTML = renderDeliverablesPanel(currentState);
      simPanelEl.innerHTML = renderSimPanel(currentState);
      office.setState(currentState.members, currentState.tasks);
      clockDisplayEl.textContent = `⏱ ${fmtTime(currentState.now)}`;
    } else {
      pipelinePanelEl.innerHTML = "";
      taskPanelEl.innerHTML = "";
      alertPanelEl.innerHTML = "";
      meetingPanelEl.innerHTML = "";
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
  } else if (action === "submit-meeting") {
    const ta = document.getElementById("meeting-text") as HTMLTextAreaElement | null;
    const text = ta?.value.trim();
    if (!text) return toast("회의 내용을 입력하세요.");
    guarded(async () => {
      const result = await api.submitMeeting(projectId, text);
      setState(result);
      toast(`회의 요약 완료 — 액션 아이템 ${result.newTasks.length}건이 신규 작업으로 생성됨.`);
      if (ta) ta.value = "";
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
