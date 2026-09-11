"use client";

import { useEffect, useState, useMemo, useRef, Fragment, type Dispatch, type SetStateAction, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import {
  FileText, Plus, Bot, Loader2, Send, CheckCircle2, XCircle,
  AlertCircle, Clock, RotateCcw, MessageSquare, X, FolderKanban,
  Download, Printer, Trash2, Save, Pencil, Lock, ChevronDown, Briefcase,
  UserIcon, CalendarIcon, FileSpreadsheet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { NewDocumentModal } from "@/components/projects/NewDocumentModal";
import { ProposalTemplate, type ProposalEvidence } from "@/components/documents/ProposalTemplate";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import { exportReqSpecExcel } from "@/lib/exportReqSpecExcel";
import { exportReqSpecPptx } from "@/lib/exportReqSpecPptx";
import type { ProposalDoc, ReqSpecDoc } from "@/lib/documentTemplates";
import { Toast } from "@/components/ui/Toast";
import {
  bareStatus, stepDone, stageOf,
  PIPELINE_STEPS, PIPELINE_TAB_LABEL,
  type BareStatus, type PipelineTab,
} from "@/lib/documentPipeline";

// ── Django 응답 shape ──────────────────────────────────────────
type SpecStatusCode = "PROPOSAL_DRAFT" | "PROPOSAL_PENDING_REVIEW" | "PROPOSAL_APPROVED" | "PROPOSAL_REJECTED";

type SpecDto = {
  id: number;
  meeting: number;
  title: string;
  overview: string | null;
  problem_definition: string | null;
  target_users: string | null;
  key_features: string | null;
  goals: string | null;
  tech_stack: string | null;
  final_decisions: string | null;
  evidence_data: string | null;
  period_start: string | null;
  period_end: string | null;
  status_code: string | null;
  status_info: { code_id: SpecStatusCode; code_name: string } | null;
  reviewer: number | null;
  reviewer_name: string | null;
  review_comment: string | null;
  created_at: string;
  updated_at: string;
};

type ReqItemDto = {
  related_feature?: string;
  input_output?: string;
  acceptance_criteria?: string;
  note?: string;
  source?: string;
  review_status?: string;

  id: number;
  req_def: number;
  req_code: string;
  req_name: string;
  description: string;
  priority_code: string | null;
  priority_info: { code_id: string; code_name: string } | null;
  category?: string | null;
  category_2?: string | null;
  difficulty?: string | null;
  order: number;
};

type ReqDefStatusCode = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";

type ReqDefDto = {
  id: number;
  spec: number;
  spec_id: number;
  spec_title: string;
  project: number;
  project_name: string;
  title: string;
  version: string;
  description?: string | null;
  status_code: string | null;
  status_info: { code_id: ReqDefStatusCode; code_name: string } | null;
  reject_reason: string | null;
  created_by: number | null;
  created_by_name: string;
  items: ReqItemDto[];
  created_at: string;
  updated_at: string;
};

type NoteDto = {
  id: number;
  project: number | null;
  title: string;
  content: string;
  summary_content: string | null;
  meeting_date: string | null;
  attendees: string | null;
  status: string;
  status_display: string;
  created_by: number;
  created_by_name: string;
  spec_documents: SpecDto[];
  created_at: string;
  updated_at: string;
};

type ProjectDto = { id: number; name: string };

type TaskAssignmentDto = {
  id: number;
  task_no: string | null;
  req_item: number;
  req_code: string;
  req_name: string;
  assigned_user: number;
  assigned_user_name: string;
  title: string;
  description: string | null;
  estimated_hours: number | null;
  assignment_reason: string | null;
  epic_no: string;
  epic_title: string;
  start_date: string | null;
  end_date: string | null;
  status_info: { code_id: string; code_name: string } | null;
};

// ── 업무 배분 (2단계 확정 플로우) ──────────────────────────────
// generate-tasks가 반환하는 미리보기 제안 하나. DB에는 아직 저장되지 않았다.
type TaskSuggestionDto = {
  unit_id: string;
  source_req_id: string;
  title: string;
  description: string;
  estimated_hours: number;
  difficulty_reason: string | null;
  epic_no: string;
  epic_title: string;
  assignee_id: number | null;
  assignee_name: string | null;
  score: number | null;
  tech_fit: string | null;
  workload_fit: string | null;
  experience_fit: string | null;
  review_required: boolean;
  hold_explanation: string | null;
  suggested_start_date: string | null;
  suggested_end_date: string | null;
  feature_area: string | null; // 2026-09-11 (Phase 2): 같은 기능 묶음(WorkPackage) 라벨
  schedule_reason: string | null; // 2026-09-11 (Phase 4): 이 날짜에 놓인 이유(결정적)
};

// 2026-09-10 (Phase 0): 남는 프로젝트 기간을 업무 사이 갭으로 숨기지 않고 PM에게
// 그대로 보여주기 위해 generate-tasks 응답에 추가된 요약.
type ScheduleSummaryDto = {
  projected_finish_date: string | null; // 마지막 업무 종료일
  project_buffer_days: number;          // 종료일까지 남는 평일 수 (음수면 초과 일수)
  exceeds_project_period: boolean;      // 일정이 프로젝트 기간을 넘겼는지
  project_start_date: string;
  project_end_date: string;
};

// 2026-09-11 (Phase 3): AI가 "이 기능 묶음은 한 사람이 아니라 여러 명이 나눠 맡는 게
// 낫다"고 판단한 항목. reason은 PM에게 그대로 노출.
type PackageSplitDto = { package_id: string; reason: string };

// 2026-09-11 (Phase 4): PM이 확정 전 손봐야 할 항목(결정적 집계) + LLM 브리핑.
type PlanReviewDto = {
  held_units: { unit_id: string; title: string; reason: string }[];
  over_period_units: { unit_id: string; title: string; assignee_name: string | null }[];
  needs_attention: boolean;
};
type PlanBriefingDto = { risks: string[]; checkpoints: string[] };

// PM이 화면에서 편집 중인 행 하나 — 제안값에서 시작하되 담당자/일정을 직접 바꿀 수 있다.
type TaskDraft = {
  unit_id: string;
  source_req_id: string;
  title: string;
  description: string;
  estimated_hours: number;
  difficulty_reason: string | null;
  epic_no: string;
  epic_title: string;
  assignee_id: number | null;
  score: number | null;
  tech_fit: string | null;
  workload_fit: string | null;
  experience_fit: string | null;
  hold_explanation: string | null;
  feature_area: string | null; // 2026-09-11 (Phase 2)
  schedule_reason: string | null; // 2026-09-11 (Phase 4)
  start_date: string; // yyyy-mm-dd, <input type="date"> 용 — 없으면 빈 문자열
  end_date: string;
};

type Member = { id: number; name: string; jobRoleCode: string | null };

// 업무 자체엔 "직무" 필드가 없어서, 담당자 계정의 job_role_code로 대신 집계한다.
// 예상 인원 요약 박스에 쓸 카테고리만 라벨을 붙이고 나머지(풀스택/PM/QA/디자이너/미지정)는
// "미분류"로 묶는다.
const JOB_ROLE_LABEL: Record<string, string> = {
  BACKEND: "백엔드",
  FRONTEND: "프론트",
  DATA_ENGINEER: "데이터",
  DEVOPS: "데브옵스",
};
const roleLabelOf = (code: string | null) => (code && JOB_ROLE_LABEL[code]) || "미분류";

const toDateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

const suggestionToDraft = (s: TaskSuggestionDto): TaskDraft => ({
  unit_id: s.unit_id,
  source_req_id: s.source_req_id,
  title: s.title,
  description: s.description,
  estimated_hours: s.estimated_hours,
  difficulty_reason: s.difficulty_reason,
  epic_no: s.epic_no,
  epic_title: s.epic_title,
  assignee_id: s.assignee_id,
  score: s.score,
  tech_fit: s.tech_fit,
  workload_fit: s.workload_fit,
  experience_fit: s.experience_fit,
  hold_explanation: s.hold_explanation,
  feature_area: s.feature_area,
  schedule_reason: s.schedule_reason,
  start_date: toDateInput(s.suggested_start_date),
  end_date: toDateInput(s.suggested_end_date),
});

// 담당자별로 업무 막대를 배치하는 간트 차트에 넘길 공통 아이템 — heyzzabi2의 GanttItem과
// 동일한 모양이라 draft/confirmed 둘 다 이걸로 변환해서 같은 GanttChart를 재사용한다.
type GanttItem = { id: string; title: string; assigneeName: string; start: string; end: string };

const STATUS_META: Record<BareStatus, { label: string; className: string; icon: any }> = {
  DRAFT: { label: "초안", className: "bg-muted text-muted-foreground", icon: FileText },
  PENDING_REVIEW: { label: "검토 요청중", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  APPROVED: { label: "승인됨", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
  REJECTED: { label: "반려됨", className: "bg-red-500/10 text-red-500", icon: XCircle },
};

// 요구사항 항목의 우선순위(CommonCode REQ_PRIORITY 그룹, code_name 기준) 한글 표시 + 배지 색.
// 설명 하단에 회색 텍스트로만 있어서 눈에 안 띈다는 피드백 — 별도 컬럼으로 빼고 상/중/하를
// 신호등처럼(급함=빨강, 보통=주황, 낮음=회색) 색으로 구분한다.
const PRIORITY_LABEL: Record<string, string> = { HIGH: "상", MEDIUM: "중", LOW: "하" };
const PRIORITY_BADGE_CLASS: Record<string, string> = {
  HIGH: "bg-red-500/10 text-red-500",
  MEDIUM: "bg-amber-500/10 text-amber-500",
  LOW: "bg-slate-500/10 text-slate-400",
};
// 우선순위 드롭박스 옵션 — CommonCode REQ_PRIORITY 그룹의 실제 code_id 값(PRIORITY_HIGH 등).
const PRIORITY_OPTIONS: { code_id: string; label: string }[] = [
  { code_id: "PRIORITY_HIGH", label: "상" },
  { code_id: "PRIORITY_MEDIUM", label: "중" },
  { code_id: "PRIORITY_LOW", label: "하" },
];

// 코드의 마지막 "-NNN" 세부번호를 뗀 그룹 부분(FR-01-003 -> FR-01). 같은 그룹 안에서는
// +버튼으로 끼워넣지 않는다(사용자 요청 — FR-01-001과 FR-01-002 사이엔 없어야 함) —
// 그룹이 바뀌는 경계(예: FR-01-003과 FR-02-001 사이)에서만 새 항목을 추가할 수 있다.
function groupOf(code: string): string {
  const m = code.match(/^(.*)-\d+$/);
  return m ? m[1] : code;
}

// 코드 끝의 숫자를 1 증가시킨다(FR-01-003 -> FR-01-004). 자릿수는 유지(001, 01 등).
// 숫자로 안 끝나면 원본 그대로 반환.
function incrementCode(code: string): string {
  const m = code.match(/^(.*?)(\d+)$/);
  if (!m) return code;
  const [, prefix, numStr] = m;
  const next = String(parseInt(numStr, 10) + 1).padStart(numStr.length, "0");
  return prefix + next;
}

// "FR-01-003" -> {prefix:"FR", group:"01", seq:"003"} — 하단 항목 추가 폼에서 분류/그룹
// 드롭박스와 다음 번호 자동계산에 쓴다. 형식이 안 맞으면 null.
function parseCode(code: string): { prefix: "FR" | "NFR"; group: string; seq: string } | null {
  const m = code.match(/^(FR|NFR)-(\d+)-(\d+)$/);
  if (!m) return null;
  return { prefix: m[1] as "FR" | "NFR", group: m[2], seq: m[3] };
}

// 우선순위 정렬용 가중치 — 상단 컬럼 헤더 클릭 정렬(엑셀처럼)에 사용.
const PRIORITY_SORT_WEIGHT: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 };

function specToProposalDoc(spec: SpecDto): ProposalDoc {
  return {
    projectOverview: spec.overview ?? "",
    problemDefinition: spec.problem_definition ?? "",
    projectGoals: spec.goals ?? "",
    target: spec.target_users ?? "",
    features: spec.key_features ?? "",
    techStackConstraints: spec.tech_stack ?? "",
    finalDecisions: spec.final_decisions ?? "",
    projectPeriod: { start: spec.period_start ?? "", end: spec.period_end ?? "" },
  };
}

function proposalDocToPatch(doc: ProposalDoc) {
  return {
    overview: doc.projectOverview,
    problem_definition: doc.problemDefinition,
    goals: doc.projectGoals,
    target_users: doc.target,
    key_features: doc.features,
    tech_stack: doc.techStackConstraints,
    final_decisions: doc.finalDecisions,
    period_start: doc.projectPeriod?.start || null,
    period_end: doc.projectPeriod?.end || null,
  };
}

// 요구사항정의서(ReqDefDto, DB에서 온 실제 데이터) -> ReqSpecDoc(엑셀/PPTX 내보내기
// 전용 스키마) 변환. 저장된 상세 필드와 출처·검토 상태를 내보낸다.
function reqDefToReqSpecDoc(reqDef: ReqDefDto): ReqSpecDoc {
  return {
    items: reqDef.items.map(item => ({
      id: item.req_code,
      category: item.category || "",
      subCategory: item.category_2 || "",
      name: item.req_name,
      description: item.description || "",
      priority: (item.priority_info?.code_name || item.priority_code || "") as any,
      relatedFeature: item.related_feature || "",
      inputOutput: item.input_output || "",
      acceptanceCriteria: item.acceptance_criteria || "",
      note: [item.source === "baseline_default" ? "추가 도출 제안·승인 필요" : item.source === "requirement_text" ? "기획서 근거" : "", item.review_status ? `AI 항목 상태: ${item.review_status} (문서 승인과 별개)` : "", item.note].filter(Boolean).join(" / "),
    })),
  };
}

// "기획서 생성"/"검토요청" 버튼은 작성자 본인만 보이는데, 삭제 버튼엔 그 체크가 빠져있었다
// (실제로 다른 사람이 시작한 초안도 지울 수 있는 상태였음) — PM은 검토 권한상 예외로 허용.
const isNoteDeletable = (note: NoteDto, currentUserId: string | undefined, isPM: boolean) => {
  if (!isPM && String(note.created_by) !== currentUserId) return false;
  const spec = note.spec_documents[0];
  if (!spec) return true;
  const s = bareStatus(spec);
  return s === "DRAFT" || s === "REJECTED";
};

export default function DocumentsPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";

  const [project, setProject] = useState<ProjectDto | null>(null);
  const [notes, setNotes] = useState<NoteDto[]>([]);
  const [reqDefs, setReqDefs] = useState<ReqDefDto[]>([]);
  const [taskAssignments, setTaskAssignments] = useState<TaskAssignmentDto[]>([]);
  // 업무배분 2단계 확정 플로우 — generate-tasks 응답(제안)을 편집 중인 임시 상태.
  // null/빈 배열이면 "리뷰 중이 아님"(진짜 배정 목록 taskAssignments를 보여줌).
  const [taskDrafts, setTaskDrafts] = useState<TaskDraft[] | null>(null);
  const [taskDraftsReqDefId, setTaskDraftsReqDefId] = useState<number | null>(null);
  // 2026-09-10 (Phase 0): generate-tasks가 돌려준 일정 요약(예상 완료일 / 프로젝트 버퍼).
  const [scheduleSummary, setScheduleSummary] = useState<ScheduleSummaryDto | null>(null);
  const [packageSplits, setPackageSplits] = useState<PackageSplitDto[]>([]); // 2026-09-11 (Phase 3)
  const [planReview, setPlanReview] = useState<PlanReviewDto | null>(null); // 2026-09-11 (Phase 4)
  const [planBriefing, setPlanBriefing] = useState<PlanBriefingDto | null>(null); // 2026-09-11 (Phase 4)
  const [generatingTasks, setGeneratingTasks] = useState(false);
  const [confirmingTasks, setConfirmingTasks] = useState(false);
  const [reassigningTaskId, setReassigningTaskId] = useState<number | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<PipelineTab>("proposal");
  const [newDocModalOpen, setNewDocModalOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<
    { kind: "spec"; specId: number } | { kind: "reqdef"; specId: number; reqDefId: number } | null
  >(null);
  const [rejectReason, setRejectReason] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const fetchAll = async (preferredProjectId?: number) => {
    setLoading(true);
    setError("");
    try {
      const projects = await apiFetch<ProjectDto[]>("/api/projects/");
      const current = preferredProjectId
        ? projects.find(p => p.id === preferredProjectId) ?? projects[0]
        : projects[0];
      setProject(current ?? null);
      if (current) {
        const [noteList, reqDefList] = await Promise.all([
          apiFetch<NoteDto[]>(`/api/meetings/notes/?project=${current.id}`),
          apiFetch<ReqDefDto[]>("/api/requirements/").catch(() => []),
        ]);
        setNotes(noteList);
        setReqDefs(reqDefList);
      } else {
        setNotes([]);
        setReqDefs([]);
      }
    } catch (err: any) {
      setError(err.message || "목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  // 담당자 변경(재배정) 드롭다운 + 배분 리뷰 화면의 담당자 선택에 쓸 팀원 목록. 전용
  // 엔드포인트가 없어서(heyzzabi2와 달리) 기존 /api/users/를 재사용해 이름만 뽑아 쓴다.
  useEffect(() => {
    // /api/users/ 응답에는 full_name 필드가 없다(실측 확인) — lib/api/mappers.ts의
    // toUser()와 동일한 규칙(성+이름, 둘 다 없으면 username)으로 표시 이름을 만든다.
    apiFetch<any[]>("/api/users/")
      .then(list => setMembers(list.map(u => ({
        id: u.id,
        name: u.first_name || u.last_name ? `${u.last_name ?? ""}${u.first_name ?? ""}` : (u.full_name || u.username || `#${u.id}`),
        jobRoleCode: u.job_role_info?.code_id ?? null,
      }))))
      .catch(() => {});
  }, []);

  const sortedNotes = useMemo(
    () => notes.slice().sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
    [notes]
  );
  const selectedNote = useMemo(
    () => sortedNotes.find(n => n.id === selectedNoteId) ?? sortedNotes[0] ?? null,
    [sortedNotes, selectedNoteId]
  );
  useEffect(() => {
    if (!selectedNoteId && sortedNotes.length > 0) setSelectedNoteId(sortedNotes[0].id);
  }, [sortedNotes, selectedNoteId]);
  // taskDrafts/taskDraftsReqDefId는 selectedNote와 무관한 전역 state라, 문서를 바꿔도
  // 저절로 안 지워진다 — A 문서에서 "업무 배분 실행"으로 draft를 만든 뒤 확정하지 않고
  // B 문서로 넘어가면, B의 배분 화면에 A의 draft가 그대로 보이고 그 상태로 "배분 확정"을
  // 누르면 B의 spec에 A의 req_def_id로 확정 요청이 나가는 사고로 이어진다(실제로 코드
  // 추적해 확인). 선택된 문서가 바뀔 때마다 무조건 리셋해 이 경로를 원천 차단한다.
  useEffect(() => {
    setTaskDrafts(null);
    setTaskDraftsReqDefId(null);
  }, [selectedNoteId]);
  // 업무배분 탭을 열었을 때 이미 배분된 업무가 있으면 보여준다(재배분 직후뿐 아니라
  // 문서를 다시 열었을 때도).
  useEffect(() => {
    if (selectedNote?.project) fetchTaskAssignments(selectedNote.project);
    else setTaskAssignments([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNote?.project]);
  // reqDef/taskAssignments를 아는 채로 stageOf/stepDone을 호출하기 위한 헬퍼 —
  // 요구사항정의서 승인·업무배분 확정까지 반영해 "지금 이 문서가 실제로 어디까지
  // 왔는지" 정확히 판단한다(documentPipeline.ts 참고).
  const reqDefFor = (spec: SpecDto | null) => (spec ? reqDefs.find(r => r.spec === spec.id) ?? null : null);
  const hasConfirmedTasksFor = (reqDef: ReqDefDto | null) => {
    if (!reqDef) return false;
    const itemIds = new Set(reqDef.items.map(i => i.id));
    return taskAssignments.some(t => itemIds.has(t.req_item));
  };

  // 문서를 고르면(직접 클릭이든, 등록 직후 자동이든) 항상 "그 문서가 지금 있는 단계"를
  // 첫 화면으로 보여준다 — heyzzabi2와 동일한 동작.
  const selectNote = (note: NoteDto) => {
    setSelectedNoteId(note.id);
    const spec = note.spec_documents[0] ?? null;
    const reqDef = reqDefFor(spec);
    setActiveTab(stageOf(spec, reqDef, hasConfirmedTasksFor(reqDef)));
  };
  // 지금 보던 탭이 승인/확정으로 "방금" 완료 처리됐을 때만(=상태가 실제로 바뀐 순간)
  // 자동으로 다음 단계로 넘어간다. done이 항상 클릭 가능해진 뒤로(위 stepper 참고)
  // activeTab이 바뀔 때마다 이 조건을 다시 평가하면, 완료된 과거 탭을 수동으로
  // 눌러 돌아가는 즉시 이 effect가 "done이니까"라며 곧바로 다음 단계로 도로 튕겨내는
  // 버그가 생긴다(실제로 재현해서 확인) — 그래서 activeTab을 의존성에서 빼고, 노트별로
  // 마지막에 본 상태 스냅샷과 비교해 "진짜로 상태가 바뀐 경우"에만 넘어가게 한다.
  const lastStageKeyRef = useRef<Record<number, string>>({});
  useEffect(() => {
    if (!selectedNote) return;
    const spec = selectedNote.spec_documents[0] ?? null;
    const reqDef = reqDefFor(spec);
    const hasConfirmedTasks = hasConfirmedTasksFor(reqDef);
    const stageKey = `${spec?.status_info?.code_id ?? ""}|${reqDef?.status_info?.code_id ?? ""}|${hasConfirmedTasks}`;
    const prevKey = lastStageKeyRef.current[selectedNote.id];
    lastStageKeyRef.current[selectedNote.id] = stageKey;
    if (prevKey !== undefined && prevKey !== stageKey && stepDone(spec, activeTab, reqDef, hasConfirmedTasks)) {
      setActiveTab(stageOf(spec, reqDef, hasConfirmedTasks));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNote?.id, selectedNote?.spec_documents[0]?.status_code, reqDefs, taskAssignments]);

  const replaceNote = (updated: NoteDto) => {
    setNotes(prev => prev.map(n => (n.id === updated.id ? updated : n)));
  };
  const refetchNote = async (noteId: number) => {
    const note = await apiFetch<NoteDto>(`/api/meetings/notes/${noteId}/`);
    replaceNote(note);
  };

  const handleGenerateSpec = async (note: NoteDto) => {
    setBusy(`${note.id}-generate`);
    try {
      await apiFetch(`/api/meetings/notes/${note.id}/analyze/`, { method: "POST" });
      await refetchNote(note.id);
      setToastMessage("기획서 생성이 완료되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "기획서 생성에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleSaveNoteContent = async (note: NoteDto, content: string) => {
    setBusy(`${note.id}-save-raw`);
    try {
      const updated = await apiFetch<NoteDto>(`/api/meetings/notes/${note.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ content }),
      });
      replaceNote(updated);
    } catch (err: any) {
      setErrorToast(err.message || "저장에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleSavePeriod = async (note: NoteDto, spec: SpecDto, period: { start: string; end: string }) => {
    setBusy(`${note.id}-save-period`);
    try {
      const updated = await apiFetch<SpecDto>(`/api/meetings/specs/${spec.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ period_start: period.start || null, period_end: period.end || null }),
      });
      replaceNote({ ...note, spec_documents: note.spec_documents.map(s => s.id === updated.id ? updated : s) });
    } catch (err: any) {
      setErrorToast(err.message || "저장에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleSaveSpec = async (note: NoteDto, spec: SpecDto, doc: ProposalDoc) => {
    setBusy(`${note.id}-save-spec`);
    try {
      await apiFetch(`/api/meetings/specs/${spec.id}/`, {
        method: "PATCH",
        body: JSON.stringify(proposalDocToPatch(doc)),
      });
      await refetchNote(note.id);
    } catch (err: any) {
      setErrorToast(err.message || "저장에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleSubmitReview = async (note: NoteDto, spec: SpecDto) => {
    // 프로젝트 기간을 안 정하고 검토요청하면 나중에 업무배분(간트차트 일정 계산 등)이
    // 기간을 기준으로 돌아가는데 기준 자체가 없어진다 — 검토요청 전에 반드시 채우게 막는다
    // (사용자 요청).
    if (!spec.period_start || !spec.period_end) {
      setErrorToast("프로젝트 기간을 입력해주세요.");
      return;
    }
    setBusy(`${note.id}-submit`);
    try {
      await apiFetch(`/api/meetings/specs/${spec.id}/submit-review/`, { method: "PATCH" });
      await refetchNote(note.id);
      setToastMessage("검토요청이 완료되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "검토 요청에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleApprove = async (note: NoteDto, spec: SpecDto) => {
    setBusy(`${note.id}-approve`);
    try {
      await apiFetch(`/api/meetings/specs/${spec.id}/approve/`, { method: "POST" });
      await refetchNote(note.id);
    } catch (err: any) {
      setErrorToast(err.message || "승인에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleReject = async () => {
    if (!rejectTarget || !rejectReason.trim() || !selectedNote) return;
    setBusy(`${selectedNote.id}-reject`);
    try {
      if (rejectTarget.kind === "spec") {
        await apiFetch(`/api/meetings/specs/${rejectTarget.specId}/reject/`, {
          method: "POST",
          body: JSON.stringify({ reason: rejectReason }),
        });
        await refetchNote(selectedNote.id);
      } else {
        const updated = await apiFetch<ReqDefDto>(`/api/requirements/${rejectTarget.specId}/`, {
          method: "PATCH",
          body: JSON.stringify({ status_code: "REJECTED", reject_reason: rejectReason }),
        });
        setReqDefs(prev => prev.map(r => r.id === rejectTarget.reqDefId ? updated : r));
      }
      setRejectTarget(null);
      setRejectReason("");
    } catch (err: any) {
      setErrorToast(err.message || "반려에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteNote = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiFetch(`/api/meetings/notes/${deleteTarget.id}/`, { method: "DELETE" });
      setNotes(prev => prev.filter(n => n.id !== deleteTarget.id));
      if (selectedNoteId === deleteTarget.id) setSelectedNoteId(null);
      setDeleteTarget(null);
    } catch (err: any) {
      setErrorToast(err.message || "삭제에 실패했습니다.");
    } finally {
      setDeleting(false);
    }
  };

  // ── 요구사항 정의서 관련 핸들러 ────────────────────────────────
  const handleCreateReqDef = async (note: NoteDto, spec: SpecDto) => {
    setBusy(`${spec.id}-create-reqdef`);
    try {
      await apiFetch("/api/requirements/", {
        method: "POST",
        body: JSON.stringify({
          spec: spec.id,
          project: note.project,
          title: `${spec.title} 요구사항정의서`,
          version: "v1.0",
        }),
      });
      const allReqDefs = await apiFetch<ReqDefDto[]>("/api/requirements/");
      setReqDefs(allReqDefs);
      setToastMessage("요구사항 정의서가 생성되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "요구사항 정의서 생성에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleExtractItems = async (specId: number, reqDefId: number) => {
    setBusy(`reqdef-${reqDefId}-extract`);
    try {
      const updatedReqDef = await apiFetch<ReqDefDto>(`/api/requirements/${specId}/extract/`, {
        method: "POST",
      });
      setReqDefs(prev => prev.map(r => r.id === reqDefId ? updatedReqDef : r));
      const itemCount = updatedReqDef.items?.length || 0;
      setToastMessage(`요구사항정의서가 재생성되었습니다 (${itemCount}건)`);
    } catch (err: any) {
      setErrorToast(err.message || "요구사항정의서 재생성에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 백엔드 requirements/urls.py에는 <reqDefId>/items/ 같은 중첩 경로가 없다(items/ 하나뿐,
  // req_def는 body로 받음) — 중첩 경로로 호출하면 404가 난다(직접 재현해서 확인).
  // order는 "이 행과 저 행 사이에 끼워넣기"를 표현하는 값(두 이웃의 order 중간값) —
  // RequirementSection이 어느 +버튼을 눌렀는지 보고 계산해서 넘긴다.
  const handleAddItem = async (reqDefId: number, item: { req_code: string; req_name: string; description: string; order: number; priority_code: string | null }) => {
    setBusy(`reqdef-${reqDefId}-additem`);
    try {
      const newItem = await apiFetch<ReqItemDto>(`/api/requirements/items/`, {
        method: "POST",
        body: JSON.stringify({ req_def: reqDefId, ...item }),
      });
      setReqDefs(prev => prev.map(r => r.id === reqDefId
        ? { ...r, items: [...r.items, newItem].sort((a, b) => a.order - b.order) }
        : r
      ));
      setToastMessage("요구사항 항목이 추가되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "항목 추가에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 백엔드에 방금 추가된 엔드포인트(/api/requirements/items/{id}/ PATCH/DELETE) — 팀원이
  // 실제로 구현·배포한 걸 확인하고 연동한다.
  const handleUpdateItem = async (reqDefId: number, itemId: number, patch: { req_name: string; description: string; priority_code?: string | null }) => {
    setBusy(`reqitem-${itemId}-update`);
    try {
      const updated = await apiFetch<ReqItemDto>(`/api/requirements/items/${itemId}/`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setReqDefs(prev => prev.map(r => r.id === reqDefId ? { ...r, items: r.items.map(it => it.id === itemId ? updated : it) } : r));
      setToastMessage("요구사항 항목이 수정되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "항목 수정에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteItem = async (reqDefId: number, itemId: number) => {
    setBusy(`reqitem-${itemId}-delete`);
    try {
      await apiFetch(`/api/requirements/items/${itemId}/`, { method: "DELETE" });
      setReqDefs(prev => prev.map(r => r.id === reqDefId ? { ...r, items: r.items.filter(it => it.id !== itemId) } : r));
      setToastMessage("요구사항 항목이 삭제되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "항목 삭제에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 요구사항정의서 상태 전이 — 전용 엔드포인트는 아직 없어서(기획서 쪽처럼 /submit-review/,
  // /approve/가 따로 없음) 일반 PATCH로 status_code만 바꾼다. DRAFT/REJECTED에서 작성자가
  // "검토요청"을 누르면 PENDING_REVIEW로, PM이 승인하면 APPROVED로 넘어간다(RequirementSection
  // 참고). 반려(REJECTED)는 사유 입력이 필수라 이 함수를 안 거치고 rejectTarget 모달 →
  // handleReject가 reject_reason과 함께 별도로 처리한다.
  const handleReqDefStatusChange = async (spec: SpecDto, reqDefId: number, statusCode: "PENDING_REVIEW" | "APPROVED") => {
    setBusy(`reqdef-${reqDefId}-${statusCode.toLowerCase()}`);
    try {
      const updated = await apiFetch<ReqDefDto>(`/api/requirements/${spec.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: statusCode }),
      });
      setReqDefs(prev => prev.map(r => r.id === reqDefId ? updated : r));
      setToastMessage(
        statusCode === "APPROVED" ? "요구사항 정의서가 승인되었습니다" : "요구사항 정의서 검토를 요청했습니다"
      );
    } catch (err: any) {
      setErrorToast(err.message || "상태 변경에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const fetchTaskAssignments = async (projectId: number) => {
    try {
      const list = await apiFetch<TaskAssignmentDto[]>(`/api/tasks/assignments/?project=${projectId}`);
      setTaskAssignments(list);
    } catch (err: any) {
      setErrorToast(err.message || "업무 목록을 불러오지 못했습니다.");
    }
  };

  // heyzzabi2의 "업무 배분 실행" — 요구사항정의서 승인 후 PM이 눌러서 실제 AI
  // 파이프라인(업무생성→담당자매핑→담당자추천)을 돌린다. 이 단계는 미리보기(제안)만
  // 만들고 DB에는 아무것도 저장하지 않는다 — PM이 담당자/일정을 검토·수정한 뒤
  // "배분 확정"을 눌러야 handleConfirmTasks가 실제로 저장한다(2단계 확정 플로우).
  const handleGenerateTasks = async (spec: SpecDto, reqDefId: number) => {
    setGeneratingTasks(true);
    setBusy(`reqdef-${reqDefId}-tasks`);
    try {
      const result = await apiFetch<{ status: string; message?: string; suggestions?: TaskSuggestionDto[]; req_def_id?: number; schedule_summary?: ScheduleSummaryDto; package_splits?: PackageSplitDto[]; plan_review?: PlanReviewDto; plan_briefing?: PlanBriefingDto }>(
        `/api/requirements/${spec.id}/generate-tasks/`,
        { method: "POST" }
      );
      if (result.status !== "success") {
        setErrorToast(result.message || "업무 배분 제안 생성에 실패했습니다.");
        return;
      }
      setTaskDrafts((result.suggestions ?? []).map(suggestionToDraft));
      setTaskDraftsReqDefId(result.req_def_id ?? reqDefId);
      setScheduleSummary(result.schedule_summary ?? null); // 2026-09-10 (Phase 0)
      setPackageSplits(result.package_splits ?? []); // 2026-09-11 (Phase 3)
      setPlanReview(result.plan_review ?? null); // 2026-09-11 (Phase 4)
      setPlanBriefing(result.plan_briefing ?? null); // 2026-09-11 (Phase 4)
      setActiveTab("taskAssignment");
      setToastMessage("업무 배분 제안이 생성되었습니다. 검토 후 확정해주세요.");
    } catch (err: any) {
      setErrorToast(err.message || "업무 배분 제안 생성에 실패했습니다.");
    } finally {
      setGeneratingTasks(false);
      setBusy(null);
    }
  };

  // PM이 검토·수정한 draft를 그대로 신뢰해 저장한다(재계산 없음) — confirm-tasks가
  // 같은 요구사항정의서의 기존 배정을 지우고 새로 만들기 때문에, 취소된 draft(담당자를
  // 미배정으로 바꾼 행)는 그냥 걸러서 보내도 되고 서버가 스킵해도 되지만, 여기서는
  // 명시적으로 걸러서 보내 의도를 분명히 한다.
  const handleConfirmTasks = async (note: NoteDto, spec: SpecDto) => {
    if (!taskDrafts || taskDraftsReqDefId == null) return;
    if (!taskDrafts.some(d => d.assignee_id != null)) {
      setErrorToast("담당자가 배정된 업무가 없습니다. 최소 1건 이상 담당자를 지정해주세요.");
      return;
    }
    setConfirmingTasks(true);
    try {
      const result = await apiFetch<{ status: string; message?: string; created_count?: number }>(
        `/api/requirements/${spec.id}/confirm-tasks/`,
        {
          method: "POST",
          body: JSON.stringify({
            req_def_id: taskDraftsReqDefId,
            assignments: taskDrafts
              .filter(d => d.assignee_id != null)
              .map(d => ({
                unit_id: d.unit_id,
                source_req_id: d.source_req_id,
                title: d.title,
                description: d.description,
                estimated_hours: d.estimated_hours,
                difficulty_reason: d.difficulty_reason,
                epic_no: d.epic_no,
                epic_title: d.epic_title,
                assignee_id: d.assignee_id,
                score: d.score,
                tech_fit: d.tech_fit,
                workload_fit: d.workload_fit,
                experience_fit: d.experience_fit,
                schedule_reason: d.schedule_reason, // 2026-09-11 (Phase 4)
                start_date: d.start_date || null,
                end_date: d.end_date || null,
              })),
          }),
        }
      );
      if (result.status !== "success") {
        setErrorToast(result.message || "업무 배분 확정에 실패했습니다.");
        return;
      }
      setToastMessage(`업무 배분이 확정되었습니다 — ${result.created_count ?? 0}건`);
      setTaskDrafts(null);
      setTaskDraftsReqDefId(null);
      setScheduleSummary(null); // 2026-09-10 (Phase 0)
      setPackageSplits([]); // 2026-09-11 (Phase 3)
      setPlanReview(null); setPlanBriefing(null); // 2026-09-11 (Phase 4)
      if (note.project) await fetchTaskAssignments(note.project);
    } catch (err: any) {
      setErrorToast(err.message || "업무 배분 확정에 실패했습니다.");
    } finally {
      setConfirmingTasks(false);
    }
  };

  // 확정된 업무의 담당자를 나중에 바꾸는 경우 — 기존 PATCH 엔드포인트(/api/tasks/assignments/{id}/)를
  // 재사용한다. 전용 재배정 엔드포인트는 이 계약에 없다.
  const handleReassignTask = async (note: NoteDto, taskId: number, assigneeId: number) => {
    setReassigningTaskId(taskId);
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify({ assigned_user: assigneeId }),
      });
      setToastMessage("담당자가 변경되었습니다");
      if (note.project) await fetchTaskAssignments(note.project);
    } catch (err: any) {
      setErrorToast(err.message || "담당자 변경에 실패했습니다.");
    } finally {
      setReassigningTaskId(null);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <AlertCircle className="w-10 h-10 text-red-400/60" />
        <p className="text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <FolderKanban className="w-10 h-10 text-muted-foreground/30" />
        {isPM ? (
          <p className="text-muted-foreground">아직 프로젝트가 없습니다. 일반유저가 회의록을 등록하면 프로젝트가 자동으로 만들어집니다.</p>
        ) : (
          <>
            <p className="text-muted-foreground">아직 프로젝트가 없습니다. 새 회의록을 등록하면 프로젝트도 함께 만들 수 있습니다.</p>
            <button
              onClick={() => setNewDocModalOpen(true)}
              className="inline-flex items-center gap-2 mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" /> 새 회의록 / 문서
            </button>
          </>
        )}
        {newDocModalOpen && (
          <NewDocumentModal
            onClose={async (createdProjectId, createdNoteId) => {
              setNewDocModalOpen(false);
              await fetchAll(createdProjectId);
              if (createdNoteId) { setSelectedNoteId(createdNoteId); setActiveTab("proposal"); }
            }}
          />
        )}
      </div>
    );
  }

  const activeSpec = selectedNote?.spec_documents[0] ?? null;
  const activeReqDef = activeSpec ? reqDefs.find(r => r.spec === activeSpec.id) ?? null : null;

  return (
    <div className="w-full space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between flex-wrap gap-4 print:hidden">
        <div>
          <h1 className="text-xl font-bold">문서생성</h1>
          <p className="text-sm text-muted-foreground mt-1">
            회의록을 기반으로 기획서를 작성하고 검토·승인합니다.
          </p>
        </div>
      </div>

      {/* Pipeline stepper — 기획서 → 요구사항정의서 → 업무배분이 하나로 이어지는
          파이프라인임을 보여준다(heyzzabi2 참고). 2026-09-09 사용자 요청으로 방향을
          바꿈: "아직 안 온" 미래 단계는 미리 못 보게 잠그고(예: 요구사항정의서가 안
          끝났는데 업무배분 탭을 눌러 미리 볼 수 있던 문제), 이미 지나온 완료 단계는
          예전처럼 계속 클릭 가능하게 둔다 — 승인된 기획서를 다시 못 열어보는(PDF/PPTX
          다운로드도 못 하는) 예전 버그는 "완료=잠금"이 아니라 "미래=잠금"이라 재현되지
          않는다. 지금 진행 중인 단계는 강조 링 + 완료는 체크, 미래는 자물쇠 아이콘. */}
      <div className="flex items-center print:hidden">
        {(() => {
          const hasConfirmedTasks = hasConfirmedTasksFor(activeReqDef);
          const currentStage = stageOf(activeSpec, activeReqDef, hasConfirmedTasks);
          const currentStageIndex = PIPELINE_STEPS.indexOf(currentStage);
          return PIPELINE_STEPS.map((step, i) => {
            const done = stepDone(activeSpec, step, activeReqDef, hasConfirmedTasks);
            const isDocStage = i === currentStageIndex;
            const isViewed = activeTab === step;
            const prevDone = i > 0 ? stepDone(activeSpec, PIPELINE_STEPS[i - 1], activeReqDef, hasConfirmedTasks) : false;
            // 문서를 아직 안 골랐으면(selectedNote 없음) 잠글 기준 자체가 없으니 전부 열어둔다.
            const locked = selectedNote ? i > currentStageIndex : false;
            return (
              <Fragment key={step}>
                {i > 0 && <div className={cn("h-0.5 w-6 md:w-10 rounded-full transition-colors", prevDone ? "bg-emerald-500/50" : "bg-black/10 dark:bg-white/10")} />}
                <button
                  onClick={() => !locked && setActiveTab(step)}
                  disabled={locked}
                  title={locked ? "이전 단계를 먼저 진행해야 볼 수 있습니다." : undefined}
                  className={cn(
                    "flex items-center gap-2 pb-1 px-1 text-base font-medium transition-colors border-b-2",
                    locked
                      ? "border-transparent text-muted-foreground/40 cursor-not-allowed"
                      : isViewed ? "border-primary text-primary font-bold" : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  <span className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 transition-colors",
                    done ? "bg-emerald-500 text-white"
                      : isDocStage ? "bg-primary text-primary-foreground ring-4 ring-primary/20"
                      : "bg-black/10 dark:bg-white/10 text-muted-foreground"
                  )}>
                    {done ? <CheckCircle2 className="w-3 h-3" /> : locked ? <Lock className="w-3 h-3" /> : i + 1}
                  </span>
                  {PIPELINE_TAB_LABEL[step]}
                </button>
              </Fragment>
            );
          });
        })()}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-6 items-start">
        {/* Document list — PDF 다운로드(window.print())는 #print-area 외 나머지를
            visibility:hidden으로만 숨기는데, 이 목록은 스크롤 없이 카드 전부(100개+)를
            그대로 렌더링해서 visibility:hidden이어도 레이아웃 높이는 그대로 차지한다.
            그 결과 body 전체 높이가 목록 길이만큼 부풀어서 실제 기획서 뒤에 빈 페이지가
            수십 장 따라붙는 버그가 있었다(실제 보고됨) — print-area의 조상이 아니라
            형제 요소라 display:none(print:hidden)으로 완전히 레이아웃에서 빼도 안전하다. */}
        <div className="glass rounded-2xl border border-border p-4 space-y-3 print:hidden">
          {!isPM && (
            <button
              onClick={() => setNewDocModalOpen(true)}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" /> 새 회의록 / 문서
            </button>
          )}

          <div className="space-y-2">
            {sortedNotes.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                등록된 회의록이 없습니다.<br />회의록을 등록하세요.
              </p>
            ) : (
              sortedNotes.map(note => {
                const spec = note.spec_documents[0] ?? null;
                const s = bareStatus(spec);
                const meta = spec ? STATUS_META[s] : STATUS_META.DRAFT;
                const Icon = meta.icon;
                // 카드에 표시할 번호도 지금 이 문서가 어느 단계까지 왔는지에 맞춰 보여준다
                // — 기획서 단계면 기획서 번호, 요구사항정의서 단계(기획서 승인 완료)로
                // 넘어갔으면 요구사항정의서 번호, 아직 기획서도 없으면 회의록 번호.
                const cardReqDef = spec ? reqDefs.find(r => r.spec === spec.id) ?? null : null;
                const cardHasConfirmedTasks = hasConfirmedTasksFor(cardReqDef);
                const cardStage = stageOf(spec, cardReqDef, cardHasConfirmedTasks);
                const [numberLabel, numberValue] = !spec
                  ? ["회의록 번호", note.id]
                  : cardStage !== "proposal" && cardReqDef
                  ? ["요구사항정의서 번호", cardReqDef.id]
                  : ["기획서 번호", spec.id];
                return (
                  <div
                    key={note.id}
                    className={cn(
                      "group w-full flex items-start gap-1 p-3 rounded-xl border transition-colors",
                      selectedNote?.id === note.id
                        ? "border-primary/50 bg-primary/5"
                        : "border-transparent hover:bg-black/5 dark:hover:bg-white/5"
                    )}
                  >
                    <button onClick={() => selectNote(note)} className="flex-1 min-w-0 text-left">
                      <p className="text-[10px] font-mono text-muted-foreground/70">{numberLabel} {numberValue}</p>
                      <p className="font-semibold text-sm truncate mb-1.5">{note.title}</p>
                      {/* 미니 파이프라인 — 이 문서가 지금 3단계 중 어디에 있는지 한눈에 */}
                      <div className="flex items-center gap-1 mb-1.5">
                        {PIPELINE_STEPS.map((step, i) => (
                          <Fragment key={step}>
                            {i > 0 && <div className={cn("h-px w-3", stepDone(spec, PIPELINE_STEPS[i - 1], cardReqDef, cardHasConfirmedTasks) ? "bg-emerald-500/40" : "bg-black/10 dark:bg-white/10")} />}
                            <div
                              title={PIPELINE_TAB_LABEL[step]}
                              className={cn(
                                "w-1.5 h-1.5 rounded-full shrink-0",
                                step === cardStage ? "bg-primary ring-2 ring-primary/25" : stepDone(spec, step, cardReqDef, cardHasConfirmedTasks) ? "bg-emerald-500" : "bg-black/10 dark:bg-white/15"
                              )}
                            />
                          </Fragment>
                        ))}
                      </div>
                      <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", spec ? meta.className : "bg-black/5 dark:bg-white/5 text-muted-foreground")}>
                        <Icon className="w-3 h-3" /> {spec ? meta.label : "기획서 미생성"}
                      </span>
                      <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5">
                        <span>{new Date(note.meeting_date ?? note.updated_at).toLocaleDateString("ko-KR")}</span>
                        <span className="text-muted-foreground/60">·</span>
                        <span className="truncate">작성자 {note.created_by_name || "알 수 없음"}</span>
                      </p>
                    </button>
                    {isNoteDeletable(note, user?.id, isPM) ? (
                      <button
                        onClick={() => setDeleteTarget({ id: note.id, title: note.title })}
                        title="문서 삭제"
                        className="shrink-0 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all text-muted-foreground hover:text-red-400 hover:bg-red-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    ) : (
                      <div title="검토 요청 중이거나 승인된 문서는 삭제할 수 없습니다" className="shrink-0 p-1.5 text-muted-foreground/40">
                        <Lock className="w-3.5 h-3.5" />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div className="glass rounded-2xl border border-border p-6 min-h-[500px]">
          {!selectedNote ? (
            <div className="h-full flex items-center justify-center text-muted-foreground text-sm py-20">
              왼쪽에서 문서를 선택하거나 새로 등록해주세요.
            </div>
          ) : (
            <NoteDetail
              note={selectedNote}
              spec={activeSpec}
              reqDef={activeReqDef}
              activeTab={activeTab}
              isPM={isPM}
              currentUserId={user?.id}
              busy={busy}
              onGenerateSpec={() => handleGenerateSpec(selectedNote)}
              onSaveNoteContent={(content) => handleSaveNoteContent(selectedNote, content)}
              onSaveSpec={(spec, doc) => handleSaveSpec(selectedNote, spec, doc)}
              onSavePeriod={(spec, period) => handleSavePeriod(selectedNote, spec, period)}
              onSubmitReview={(spec) => handleSubmitReview(selectedNote, spec)}
              onApprove={(spec) => handleApprove(selectedNote, spec)}
              onReject={(spec) => setRejectTarget({ kind: "spec", specId: spec.id })}
              onCreateReqDef={(spec) => handleCreateReqDef(selectedNote, spec)}
              onExtractItems={handleExtractItems}
              onAddItem={handleAddItem}
              onUpdateItem={handleUpdateItem}
              onDeleteItem={handleDeleteItem}
              onReqDefStatusChange={handleReqDefStatusChange}
              onGenerateTasks={(spec, reqDefId) => handleGenerateTasks(spec, reqDefId)}
              onRejectReqDef={(spec, reqDefId) => setRejectTarget({ kind: "reqdef", specId: spec.id, reqDefId })}
              taskAssignments={taskAssignments}
              taskDrafts={taskDrafts}
              setTaskDrafts={setTaskDrafts}
              scheduleSummary={scheduleSummary}
              packageSplits={packageSplits}
              planReview={planReview}
              planBriefing={planBriefing}
              generatingTasks={generatingTasks}
              confirmingTasks={confirmingTasks}
              onConfirmTasks={(spec) => handleConfirmTasks(selectedNote, spec)}
              onCancelTaskDrafts={() => { setTaskDrafts(null); setTaskDraftsReqDefId(null); setScheduleSummary(null); setPackageSplits([]); setPlanReview(null); setPlanBriefing(null); }}
              members={members}
              reassigningTaskId={reassigningTaskId}
              onReassignTask={(taskId, assigneeId) => handleReassignTask(selectedNote, taskId, assigneeId)}
            />
          )}
        </div>
      </div>

      {newDocModalOpen && (
        <NewDocumentModal
          defaultProjectId={project.id}
          onClose={async (createdProjectId, createdNoteId) => {
            setNewDocModalOpen(false);
            await fetchAll(createdProjectId);
            if (createdNoteId) { setSelectedNoteId(createdNoteId); setActiveTab("proposal"); }
          }}
        />
      )}

      {rejectTarget && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <RotateCcw className="w-5 h-5" /> 반려 사유 입력
              </h3>
              <button onClick={() => setRejectTarget(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">반려 사유는 작성자에게 그대로 전달됩니다.</p>
            <div className="relative mb-4">
              <MessageSquare className="w-4 h-4 absolute left-3 top-3.5 text-muted-foreground" />
              <textarea
                autoFocus
                className="w-full pl-9 pr-4 py-3 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 resize-none h-28"
                placeholder="예: 3번 항목 재검토가 필요합니다."
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <button onClick={() => setRejectTarget(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim() || !!busy}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <XCircle className="w-4 h-4" /> 반려 처리
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4">
            <h3 className="text-xl font-bold mb-2 flex items-center gap-2 text-red-400">
              <Trash2 className="w-5 h-5" /> 문서 삭제
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              <span className="font-bold text-foreground">"{deleteTarget.title}"</span> 문서를 삭제하시겠습니까?<br />
              이 작업은 되돌릴 수 없습니다.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleDeleteNote}
                disabled={deleting}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                삭제
              </button>
            </div>
          </div>
        </div>
      )}
      <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
      <Toast message={errorToast} variant="error" onDismiss={() => setErrorToast(null)} />
    </div>
  );
}

function NoteDetail({
  note, spec, reqDef, activeTab, isPM, currentUserId, busy,
  onGenerateSpec, onSaveNoteContent, onSaveSpec, onSavePeriod, onSubmitReview, onApprove, onReject,
  onCreateReqDef, onExtractItems, onAddItem, onUpdateItem, onDeleteItem, onReqDefStatusChange,
  onGenerateTasks, taskAssignments, onRejectReqDef,
  taskDrafts, setTaskDrafts, scheduleSummary, packageSplits, planReview, planBriefing, generatingTasks, confirmingTasks, onConfirmTasks, onCancelTaskDrafts,
  members, reassigningTaskId, onReassignTask,
}: {
  note: NoteDto; spec: SpecDto | null; reqDef: ReqDefDto | null; activeTab: PipelineTab; isPM: boolean; currentUserId: string | undefined; busy: string | null;
  onGenerateSpec: () => void;
  onSaveNoteContent: (content: string) => void;
  onSaveSpec: (spec: SpecDto, doc: ProposalDoc) => void;
  onSavePeriod: (spec: SpecDto, period: { start: string; end: string }) => void;
  onSubmitReview: (spec: SpecDto) => void;
  onApprove: (spec: SpecDto) => void;
  onReject: (spec: SpecDto) => void;
  onCreateReqDef: (spec: SpecDto) => void;
  onExtractItems: (specId: number, reqDefId: number) => void;
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string; order: number; priority_code: string | null }) => void;
  onUpdateItem: (reqDefId: number, itemId: number, patch: { req_name: string; description: string; priority_code?: string | null }) => void;
  onDeleteItem: (reqDefId: number, itemId: number) => void;
  onReqDefStatusChange: (spec: SpecDto, reqDefId: number, statusCode: "PENDING_REVIEW" | "APPROVED") => void;
  onGenerateTasks: (spec: SpecDto, reqDefId: number) => void;
  onRejectReqDef: (spec: SpecDto, reqDefId: number) => void;
  taskAssignments: TaskAssignmentDto[];
  taskDrafts: TaskDraft[] | null;
  setTaskDrafts: Dispatch<SetStateAction<TaskDraft[] | null>>;
  scheduleSummary: ScheduleSummaryDto | null; // 2026-09-10 (Phase 0)
  packageSplits: PackageSplitDto[]; // 2026-09-11 (Phase 3)
  planReview: PlanReviewDto | null; // 2026-09-11 (Phase 4)
  planBriefing: PlanBriefingDto | null; // 2026-09-11 (Phase 4)
  generatingTasks: boolean;
  confirmingTasks: boolean;
  onConfirmTasks: (spec: SpecDto) => void;
  onCancelTaskDrafts: () => void;
  members: Member[];
  reassigningTaskId: number | null;
  onReassignTask: (taskId: number, assigneeId: number) => void;
}) {
  const status = bareStatus(spec);
  const meta = STATUS_META[status];
  const canGenerate = String(note.created_by) === currentUserId;
  const dateLabel = new Date(note.updated_at).toLocaleDateString("ko-KR");
  // taskAssignments는 프로젝트 단위로 통째로 가져온다(reqDef별 조회 API가 없음) — 그대로
  // 쓰면 "같은 프로젝트의 예전 요구사항정의서로 이미 배분한 기록"이 있을 때 방금 새로
  // 만든 요구사항정의서에도 "이미 배분됨"으로 잘못 표시되어 배분 실행 버튼이 스킵된
  // 것처럼 사라지는 실제 버그가 있었다 — reqDef.items에 실제로 속한 업무만 걸러낸다.
  const reqDefItemIds = new Set((reqDef?.items ?? []).map(item => item.id));
  const tasksForReqDef = taskAssignments.filter(t => reqDefItemIds.has(t.req_item));
  // 확정된 업무배분 목록 — PM은 전체를 보고, 일반 유저는 본인에게 배정된 업무만 본다
  // (heyzzabi2와 동일한 접근 제어 — 다른 사람 업무까지 보이면 안 된다는 요청).
  const visibleTaskAssignments = isPM
    ? tasksForReqDef
    : tasksForReqDef.filter(t => String(t.assigned_user) === currentUserId);

  const busyKey = (action: string) => `${note.id}-${action}`;

  const [rawDraft, setRawDraft] = useState(note.content ?? "");
  useEffect(() => { setRawDraft(note.content ?? ""); }, [note.id, note.content]);
  const rawDirty = rawDraft !== (note.content ?? "");
  const rawSaving = busy === busyKey("save-raw");
  const rawLocked = !!spec;
  // "기획서 원본"(요구사항정의서 탭) 참고 박스와 동일하게 접었다 펼 수 있게(사용자 요청) — 기본은 펼침.
  const [rawNoteOpen, setRawNoteOpen] = useState(true);
  const specLocked = status === "PENDING_REVIEW" || status === "APPROVED";
  // "기획서 생성"과 같은 기준 — 작성자 본인이 아니면 원본 회의록도 못 고친다(PM은 예외).
  // 이 체크가 빠져있어서 다른 사람이 시작한 회의록도 아무나 고칠 수 있는 상태였다.
  const canEditRaw = canGenerate || isPM;

  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<ProposalDoc | null>(null);
  useEffect(() => { setEditMode(false); setEditDraft(null); }, [note.id]);
  const editSaving = busy === busyKey("save-spec");

  const [periodDraft, setPeriodDraft] = useState({ start: spec?.period_start ?? "", end: spec?.period_end ?? "" });
  useEffect(() => {
    setPeriodDraft({ start: spec?.period_start ?? "", end: spec?.period_end ?? "" });
  }, [note.id, spec?.period_start, spec?.period_end]);
  const periodEditable = !!spec && !specLocked && !editMode;
  const handlePeriodChange = (period: { start: string; end: string }) => {
    if (!spec) return;
    setPeriodDraft(period);
    onSavePeriod(spec, period);
  };

  const startEdit = () => {
    if (!spec) return;
    setEditDraft(specToProposalDoc(spec));
    setEditMode(true);
  };
  const saveEdit = () => {
    if (!spec || !editDraft) return;
    onSaveSpec(spec, editDraft);
    setEditMode(false);
  };

  const parsedContent: ProposalDoc | null = editMode
    ? editDraft
    : (spec ? { ...specToProposalDoc(spec), projectPeriod: periodDraft } : null);

  const handlePrint = () => window.print();
  const handlePptx = async () => {
    if (!parsedContent) return;
    await exportProposalPptx(parsedContent, note.title);
  };

  // 요구사항정의서 탭 상단에 보여줄 기획서 원본 참고 박스 — heyzzabi2와 동일하게 기본은
  // 펼친 채로 시작한다(접혀 있으면 지금 보는 게 참고 박스인지 본문인지 헷갈린다는 이유).
  const [proposalRefOpen, setProposalRefOpen] = useState(true);
  useEffect(() => { setProposalRefOpen(true); }, [note.id]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          {/* 이 헤더는 note.title(회의록 제목) 바로 위라서 항상 회의록 번호로 고정한다 —
              탭에 따라 기획서/요구사항정의서 번호로 바뀌면 "회의록" 제목 위에 다른 문서
              번호가 떠서 헷갈린다는 피드백. 기획서/요구사항정의서 번호는 각 탭의 해당
              내용 바로 옆에 따로 표시한다. */}
          <p className="text-xs font-mono text-muted-foreground/70">회의록 번호 {note.id}</p>
          <h2 className="font-bold text-lg">{note.title}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            작성자 {note.created_by_name || "알 수 없음"}
            {String(note.created_by) === currentUserId && <span className="text-primary font-medium"> (나)</span>}
          </p>
          {/* 프로젝트 기간 — 기획서 검토요청 시점에 필수 입력이라(handleSubmitReview 참고) 기획서가
              하나라도 생성된 뒤엔 항상 값이 있다. 탭과 무관하게(기획서/요구사항정의서/업무배분) 공통
              헤더에 표시 — 사용자 요청으로 업무배분 화면 상단에서 바로 보여야 함. */}
          {spec?.period_start && spec?.period_end && (
            <p className="text-xs text-muted-foreground mt-0.5">
              프로젝트 기간 {spec.period_start} ~ {spec.period_end}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold", meta.className)}>
            <meta.icon className="w-3.5 h-3.5" /> {spec ? meta.label : "기획서 미생성"}
          </span>
          {/* 요구사항정의서 탭처럼 PM 승인/반려는 상단 우측(제목 옆)에 둔다 — 검토요청/
              직접수정은 하단, 승인/반려만 상단으로 통일(사용자 요청). PDF/PPTX 다운로드는
              하단 좌측 그대로. */}
          {activeTab === "proposal" && spec && isPM && status === "PENDING_REVIEW" && (
            <>
              <button
                onClick={() => onReject(spec)}
                disabled={busy === busyKey("reject")}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold hover:bg-red-500/20 disabled:opacity-50"
              >
                <XCircle className="w-3.5 h-3.5" /> 반려
              </button>
              <button
                onClick={() => onApprove(spec)}
                disabled={busy === busyKey("approve")}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500 text-white text-xs font-semibold hover:bg-emerald-600 disabled:opacity-50"
              >
                {busy === busyKey("approve") ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                승인
              </button>
            </>
          )}
        </div>
      </div>

      {spec?.review_comment && status === "REJECTED" && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div><span className="font-semibold">반려 사유:</span> {spec.review_comment}</div>
        </div>
      )}

      {/* 세 탭을 조건부 렌더링(삼항연산자로 갈아끼우기)하면 탭을 옮길 때마다 로컬 상태(예:
          직접수정 중이던 초안, 항목 추가 폼)가 통째로 날아간다 — 항상 mount해두고 CSS로만
          숨겨서 안 보이는 탭의 상태도 그대로 유지되게 한다(heyzzabi2와 동일한 이유). */}
      <div className={cn("space-y-5", activeTab !== "proposal" && "hidden")}>
      <div className="text-sm">
        <div className="flex items-center justify-between mb-2">
          <button
            type="button"
            onClick={() => setRawNoteOpen(v => !v)}
            className="flex items-center gap-1.5 text-muted-foreground font-medium hover:text-foreground transition-colors"
          >
            <ChevronDown className={cn("w-4 h-4 transition-transform shrink-0", !rawNoteOpen && "-rotate-90")} />
            원본 회의록 / 메모
            {rawLocked && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
                <Lock className="w-3 h-3" /> 기획서 생성 후에는 수정할 수 없습니다
              </span>
            )}
          </button>
          {!rawLocked && canEditRaw && rawDirty && (
            <button
              onClick={() => onSaveNoteContent(rawDraft)}
              disabled={rawSaving}
              className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 disabled:opacity-50 transition-colors"
            >
              {rawSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              저장
            </button>
          )}
        </div>
        {rawNoteOpen && (
          <textarea
            value={rawDraft}
            onChange={e => !rawLocked && canEditRaw && setRawDraft(e.target.value)}
            readOnly={rawLocked || !canEditRaw}
            placeholder="내용이 없습니다."
            title={!rawLocked && !canEditRaw ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 수정할 수 있습니다." : undefined}
            className={cn(
              "w-full h-48 bg-black/5 dark:bg-white/5 border border-border rounded-xl p-4 whitespace-pre-wrap overflow-y-auto text-muted-foreground resize-none focus:outline-none transition-all",
              (rawLocked || !canEditRaw) ? "cursor-default" : "focus:ring-2 focus:ring-primary/40"
            )}
          />
        )}
      </div>

      <p className="text-sm text-muted-foreground font-semibold flex items-center gap-2">
        기획서
        {spec && <span className="text-xs font-mono font-normal text-muted-foreground/70">기획서 번호 {spec.id}</span>}
      </p>
      <div className="border border-border rounded-xl overflow-hidden bg-black/10 dark:bg-black/30 p-4 flex flex-col items-center gap-3">
        {parsedContent ? (
          <div className="w-full max-w-[840px] max-h-[1190px] overflow-y-auto bg-white dark:bg-white">
            <div id="print-area">
              <ProposalTemplate
                doc={parsedContent}
                title={note.title} dateLabel={dateLabel}
                editable={editMode} onChange={setEditDraft}
                periodEditable={periodEditable} onPeriodChange={handlePeriodChange}
                evidence={parseProposalEvidence(spec?.evidence_data ?? null)}
              />
            </div>
          </div>
        ) : (
          <div className="w-full max-w-[840px] bg-white dark:bg-white p-10 text-center text-muted-foreground text-sm">
            {!canGenerate || isPM ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 생성할 수 있습니다." : "AI가 아직 기획서를 생성하지 않았습니다."}
          </div>
        )}
      </div>

      <div className="flex justify-end items-center gap-3 pt-2">
        {spec && (
          <div className="flex items-center gap-2 mr-auto">
            <button onClick={handlePrint} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <Printer className="w-3.5 h-3.5" /> PDF 다운로드
            </button>
            <button onClick={handlePptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <Download className="w-3.5 h-3.5" /> PPTX 다운로드
            </button>
          </div>
        )}

        {!spec && canGenerate && !isPM && (
          <button
            onClick={onGenerateSpec}
            disabled={busy === busyKey("generate")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("generate") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
            기획서 생성
          </button>
        )}

        {/* 2026-09-10: 팀원 요청으로 추가한 "재생성" 버튼 — analyze 엔드포인트가 이미
            update_or_create라 기존 기획서 위에 덮어써도 백엔드 수정 없이 안전하다. 다만
            검토요청 이후(PENDING_REVIEW/APPROVED)에는 노출하지 않는다 — 승인된 기획서 내용이
            사용자가 인지하지 못한 채 AI 재생성으로 통째로 바뀌면 안 되기 때문(검토요청 버튼과
            같은 조건). "직접수정"으로 손댄 내용도 재생성하면 사라지므로 실행 전 확인창을 띄운다. */}
        {spec && !isPM && canGenerate && (status === "DRAFT" || status === "REJECTED") && (
          <button
            onClick={() => {
              if (window.confirm("기획서를 다시 생성하면 현재 내용(직접 수정한 부분 포함)이 AI 결과로 덮어써집니다. 계속하시겠습니까?")) {
                onGenerateSpec();
              }
            }}
            disabled={busy === busyKey("generate")}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            {busy === busyKey("generate") ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
            재생성
          </button>
        )}

        {/* 검토요청은 하단, 승인/반려는 상단 우측 — "직접수정"도 하단에 있어서 사용자
            흐름상 하단에 두는 게 더 자연스럽다는 판단으로 다시 하단으로 내렸다. */}
        {spec && !isPM && canGenerate && (status === "DRAFT" || status === "REJECTED") && (
          <button
            onClick={() => onSubmitReview(spec)}
            disabled={busy === busyKey("submit")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("submit") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            검토요청
          </button>
        )}

        {/* "기획서 생성"/"검토요청"과 같은 기준(작성자 본인, PM은 예외)으로 맞춘다 —
            이 체크가 빠져있어서 다른 사람이 시작한 초안도 고칠 수 있는 상태였다. */}
        {spec && (status === "REJECTED" || status === "DRAFT") && (canGenerate || isPM) && !editMode && (
          <button
            onClick={startEdit}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors"
          >
            <Pencil className="w-4 h-4" /> 직접 수정
          </button>
        )}

        {spec && (status === "REJECTED" || status === "DRAFT") && editMode && (
          <>
            <button
              onClick={() => setEditMode(false)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors"
            >
              취소
            </button>
            <button
              onClick={saveEdit}
              disabled={editSaving}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
            >
              {editSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              저장
            </button>
          </>
        )}

        {spec && !isPM && status === "PENDING_REVIEW" && (
          <span className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-muted text-muted-foreground text-sm font-bold">
            <Clock className="w-4 h-4" /> 요청완료
          </span>
        )}

        {/* 승인/반려는 상단 우측(제목 옆)으로 옮겼다 — 요구사항정의서 탭과 위치 통일. */}
      </div>
      </div>

      {/* 요구사항정의서 탭 — heyzzabi2와 동일하게 위에는 근거가 된 기획서 원본을 접었다 폈다
          볼 수 있게 참고 박스로 보여주고, 아래에 실제 요구사항정의서 본문/조작을 둔다. */}
      <div className={cn("space-y-5", activeTab !== "reqSpec" && "hidden")}>
        <div className="text-sm">
          <button
            type="button"
            onClick={() => setProposalRefOpen(v => !v)}
            className="w-full flex items-center justify-between gap-2 text-muted-foreground font-medium hover:text-foreground transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <ChevronDown className={cn("w-4 h-4 transition-transform", !proposalRefOpen && "-rotate-90")} />
              기획서 원본
            </span>
            <span className="flex items-center gap-2">
              {/* 회의록/요구사항정의서는 각자 번호가 보이는데 기획서 원본 박스만 없어서
                  추가 — 다른 두 곳과 동일한 스타일(font-mono, 흐린 색)로 맞춘다. */}
              {spec && <span className="text-xs font-mono font-normal text-muted-foreground/70">기획서 번호 {spec.id}</span>}
              <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
                <meta.icon className="w-3 h-3" /> {spec ? meta.label : "기획서 미생성"}
              </span>
            </span>
          </button>
          {proposalRefOpen && (
            <div className="mt-2 border border-border rounded-xl overflow-hidden max-h-64 overflow-y-auto bg-black/5 dark:bg-black/20">
              {spec ? (
                <ProposalTemplate doc={specToProposalDoc(spec)} title={note.title} dateLabel={dateLabel} />
              ) : (
                <div className="p-6 text-center text-muted-foreground text-xs">기획서 내용이 없습니다.</div>
              )}
            </div>
          )}
        </div>

        {status !== "APPROVED" ? (
          <div className="border border-dashed border-border rounded-xl p-10 text-center text-muted-foreground text-sm">
            {status === "DRAFT" && "기획서가 아직 작성 중입니다. 기획서를 검토요청하고 승인받아야 요구사항정의서를 생성할 수 있습니다."}
            {status === "PENDING_REVIEW" && "기획서가 아직 검토요청 중입니다. PM 승인 후 요구사항정의서를 생성할 수 있습니다."}
            {status === "REJECTED" && "기획서가 반려되었습니다. 기획서를 다시 작성해 승인받아야 합니다."}
          </div>
        ) : (
          <RequirementSection
            spec={spec!}
            reqDef={reqDef}
            isPM={isPM}
            canGenerate={canGenerate}
            busy={busy}
            onCreate={() => onCreateReqDef(spec!)}
            onExtract={onExtractItems}
            onAddItem={onAddItem}
            onUpdateItem={onUpdateItem}
            onDeleteItem={onDeleteItem}
            onStatusChange={(statusCode) => onReqDefStatusChange(spec!, reqDef!.id, statusCode)}
            onGenerateTasks={() => onGenerateTasks(spec!, reqDef!.id)}
            generatingTasks={!!reqDef && busy === `reqdef-${reqDef.id}-tasks`}
            onRejectClick={() => onRejectReqDef(spec!, reqDef!.id)}
            tasksAlreadyAssigned={tasksForReqDef.length > 0}
          />
        )}
      </div>

      {/* 업무배분 탭 — heyzzabi2의 TaskAssignmentPanel과 동일한 2단계(제안 검토→확정) 흐름.
          taskDrafts는 서버에 저장되는 게 아니라 PM 브라우저의 로컬 상태일 뿐이라 원래
          다른 사람 화면엔 안 뜨는 게 맞지만, 이 화면 자체가 isPM을 체크하지 않고 있어서
          같은 브라우저에서 계정을 바꾸는 등의 경우 일반 유저도 편집 화면을 보고 담당자/
          일정을 바꿀 수 있는 실제 문제가 있었다 — PM만 검토/확정 화면을 보게 막는다. */}
      <div className={cn(activeTab !== "taskAssignment" && "hidden")}>
        {taskDrafts && taskDrafts.length > 0 && isPM ? (
          <TaskDraftReview
            drafts={taskDrafts}
            setDrafts={setTaskDrafts}
            scheduleSummary={scheduleSummary}
            packageSplits={packageSplits}
            planReview={planReview}
            planBriefing={planBriefing}
            members={members}
            confirming={confirmingTasks}
            onCancel={onCancelTaskDrafts}
            onConfirm={() => spec && onConfirmTasks(spec)}
          />
        ) : taskDrafts && taskDrafts.length > 0 && !isPM ? (
          <div className="border border-dashed border-border rounded-xl p-10 flex flex-col items-center gap-3 text-center">
            <Clock className="w-8 h-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">배분 확정 전입니다. PM이 검토를 마치고 확정하면 여기에 표시됩니다.</p>
          </div>
        ) : visibleTaskAssignments.length === 0 ? (
          <div className="border border-dashed border-border rounded-xl p-10 flex flex-col items-center gap-3 text-center">
            {generatingTasks ? (
              <div className="flex flex-col items-center gap-4 py-6">
                <Loader2 className="w-9 h-9 animate-spin text-primary" />
                <p className="text-sm font-semibold text-muted-foreground">에이전트가 업무를 배분하는 중입니다…</p>
              </div>
            ) : (
              <>
                <Briefcase className="w-8 h-8 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">
                  {!isPM && tasksForReqDef.length > 0
                    ? "본인에게 배정된 업무가 없습니다."
                    : reqDef?.status_info?.code_id === "APPROVED"
                    ? "요구사항정의서 탭에서 \"업무 배분 실행\"을 누르면 여기에 결과가 표시됩니다."
                    : "요구사항정의서가 승인되면 업무 배분을 실행할 수 있습니다."}
                </p>
              </>
            )}
          </div>
        ) : (
          <TaskAssignmentList
            tasks={visibleTaskAssignments}
            members={members}
            isPM={isPM}
            reassigningTaskId={reassigningTaskId}
            onReassign={onReassignTask}
          />
        )}
      </div>
    </div>
  );
}

// 업무명/난이도/시간 배지 + 펼침형 배정근거를 함께 보여주는 공통 헤더 셀 — draft 리뷰
// 표와 확정 목록 표가 똑같은 모양을 쓰므로 하나로 뺐다(heyzzabi2 TaskAssignmentPanel 참고).
function TaskTitleCell({
  title, estimatedHours, techFit, featureArea, expanded, onToggleExpand,
}: {
  title: string; estimatedHours: number | null; techFit: string | null;
  featureArea?: string | null; // 2026-09-11 (Phase 2): 기능 묶음 라벨
  expanded: boolean; onToggleExpand: () => void;
}) {
  return (
    <button
      onClick={onToggleExpand}
      disabled={!techFit}
      className="flex items-start gap-1 font-semibold hover:text-primary transition-colors text-left disabled:cursor-default disabled:hover:text-foreground"
    >
      {techFit && <ChevronDown className={cn("w-3.5 h-3.5 transition-transform shrink-0 mt-0.5", !expanded && "-rotate-90")} />}
      <span className="min-w-0">
        <span className="block truncate">{title}</span>
        <span className="flex items-center gap-1.5 mt-0.5">
          <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-muted-foreground font-semibold">
            {estimatedHours ?? "-"}h
          </span>
          {featureArea && (
            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">
              {featureArea}
            </span>
          )}
          {techFit ? (
            <span className="text-xs font-normal text-muted-foreground line-clamp-1">{techFit}</span>
          ) : (
            <span className="text-xs font-normal text-muted-foreground/60">배정 근거 없음</span>
          )}
        </span>
      </span>
    </button>
  );
}

function ReasonRow({ techFit, workloadFit, experienceFit, scheduleReason }: { techFit: string | null; workloadFit: string | null; experienceFit: string | null; scheduleReason?: string | null }) {
  return (
    <tr className="bg-black/[0.02] dark:bg-white/[0.02]">
      <td colSpan={4} className="px-4 pb-3 pt-0">
        <ul className="text-xs text-muted-foreground space-y-1 pl-5">
          <li>🛠 기술 적합도: {techFit ?? "-"}</li>
          <li>📊 업무 여유도: {workloadFit ?? "-"}</li>
          <li>📁 유사 경험: {experienceFit ?? "-"}</li>
          {scheduleReason && <li>📅 일정 근거: {scheduleReason}</li>}
        </ul>
      </td>
    </tr>
  );
}

// AI 제안을 PM이 검토·수정하는 화면 — 아직 DB에 저장되지 않은 draft 상태만 다룬다.
// 확정("배분 확정")을 눌러야 비로소 handleConfirmTasks가 실제로 저장한다.
function TaskDraftReview({
  drafts, setDrafts, scheduleSummary, packageSplits, planReview, planBriefing, members, confirming, onCancel, onConfirm,
}: {
  drafts: TaskDraft[];
  setDrafts: Dispatch<SetStateAction<TaskDraft[] | null>>;
  scheduleSummary: ScheduleSummaryDto | null; // 2026-09-10 (Phase 0)
  packageSplits: PackageSplitDto[]; // 2026-09-11 (Phase 3)
  planReview: PlanReviewDto | null; // 2026-09-11 (Phase 4)
  planBriefing: PlanBriefingDto | null; // 2026-09-11 (Phase 4)
  members: Member[];
  confirming: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [expandedUnitId, setExpandedUnitId] = useState<string | null>(null);

  const updateDraft = (unitId: string, patch: Partial<TaskDraft>) => {
    setDrafts(prev => prev?.map(d => d.unit_id === unitId ? { ...d, ...patch } : d) ?? null);
  };

  const ganttItems: GanttItem[] = drafts
    .filter(d => d.assignee_id != null && d.start_date && d.end_date)
    .map(d => ({
      id: d.unit_id,
      title: d.title,
      assigneeName: members.find(m => m.id === d.assignee_id)?.name ?? "미배정",
      start: d.start_date,
      end: d.end_date,
    }));

  // 전부 "미배정"인 채로 확정을 누르면 서버가 저장할 게 하나도 없어 created_count=0
  // 인데도 "확정되었습니다" 성공 토스트가 뜨는 버그가 있었다(사용자 신고: "배분 확정하고
  // DB에 안 들어가는 상황"). "미배정" 자체는 AI가 워크로드/스킬 불일치로 일부러 보류
  // 추천하는 정상 값이라 드롭박스에서 없앨 수는 없으니, 최소 1건은 배정돼야 확정 버튼을
  // 누를 수 있게 막는다.
  const hasAnyAssignee = drafts.some(d => d.assignee_id != null);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        AI가 추천한 담당자와 일정입니다. 필요하면 담당자·일정을 직접 바꾼 뒤 확정하세요. 확정 전까지는 저장되지 않습니다.
      </p>
      {/* 2026-09-10 (Phase 0): 남는 기간을 업무 사이 갭으로 숨기지 않고 "프로젝트 버퍼"로 드러낸다.
          버퍼가 음수(초과)면 일정이 프로젝트 종료일을 넘어선다는 뜻이라 경고색으로 표시. */}
      {scheduleSummary?.projected_finish_date && (
        <div className={cn(
          "rounded-xl border px-4 py-3 text-sm",
          scheduleSummary.exceeds_project_period
            ? "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400"
            : "border-border bg-black/5 dark:bg-white/5 text-muted-foreground",
        )}>
          예상 완료일 <strong className="text-foreground">{scheduleSummary.projected_finish_date}</strong>
          {" · "}프로젝트 종료일 {scheduleSummary.project_end_date}
          {scheduleSummary.exceeds_project_period
            ? <> · <strong>{-scheduleSummary.project_buffer_days}일 초과</strong> — 인력 또는 기간 조정이 필요합니다</>
            : <> · 여유 <strong className="text-foreground">{scheduleSummary.project_buffer_days}일</strong> (버퍼)</>}
        </div>
      )}
      {/* 2026-09-11 (Phase 3): AI가 여러 명이 나눠 맡는 게 낫다고 판단한 기능 묶음. */}
      {packageSplits.length > 0 && (
        <div className="rounded-xl border border-border bg-black/5 dark:bg-white/5 px-4 py-3 text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">여러 담당자로 나눈 기능</span>
          <ul className="mt-1 space-y-0.5">
            {packageSplits.map(s => (
              <li key={s.package_id}>· {s.reason || s.package_id}</li>
            ))}
          </ul>
        </div>
      )}
      {/* 2026-09-11 (Phase 4): 확정 전 PM이 직접 손봐야 할 항목(결정적 집계). */}
      {planReview?.needs_attention && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          <span className="font-semibold">확정 전 확인 필요</span>
          <ul className="mt-1 space-y-0.5">
            {planReview.held_units.map(h => (
              <li key={h.unit_id}>· 담당자 미정: <strong>{h.title}</strong>{h.reason ? ` — ${h.reason}` : ""}</li>
            ))}
            {planReview.over_period_units.map(o => (
              <li key={o.unit_id}>· 기간 초과: <strong>{o.title}</strong>{o.assignee_name ? ` (${o.assignee_name})` : ""}</li>
            ))}
          </ul>
        </div>
      )}
      {/* 2026-09-11 (Phase 4): LLM이 읽고 정리한 계획 리스크·체크포인트. */}
      {planBriefing && (planBriefing.risks.length > 0 || planBriefing.checkpoints.length > 0) && (
        <div className="rounded-xl border border-border bg-black/5 dark:bg-white/5 px-4 py-3 text-sm text-muted-foreground space-y-2">
          {planBriefing.risks.length > 0 && (
            <div>
              <span className="font-semibold text-foreground">⚠ 리스크</span>
              <ul className="mt-1 space-y-0.5">{planBriefing.risks.map((r, i) => <li key={i}>· {r}</li>)}</ul>
            </div>
          )}
          {planBriefing.checkpoints.length > 0 && (
            <div>
              <span className="font-semibold text-foreground">✅ 체크포인트</span>
              <ul className="mt-1 space-y-0.5">{planBriefing.checkpoints.map((c, i) => <li key={i}>· {c}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      <CollapsibleSection title="예상 필요 인원">
        <HeadcountSummary assigneeIds={drafts.map(d => d.assignee_id)} members={members} />
      </CollapsibleSection>
      <CollapsibleSection title="업무 일정">
        <GanttChart items={ganttItems} />
      </CollapsibleSection>
      <div className="border border-border rounded-xl overflow-hidden overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-4 py-3 font-bold">업무명</th>
              <th className="px-4 py-3 font-bold w-40">담당자</th>
              <th className="px-4 py-3 font-bold w-24">적합도</th>
              <th className="px-4 py-3 font-bold w-64">시작~종료일</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {drafts.map(d => (
              <Fragment key={d.unit_id}>
                <tr className="align-top">
                  <td className="px-4 py-3">
                    <TaskTitleCell
                      title={d.title}
                      estimatedHours={d.estimated_hours}
                      techFit={d.tech_fit}
                      featureArea={d.feature_area}
                      expanded={expandedUnitId === d.unit_id}
                      onToggleExpand={() => setExpandedUnitId(v => v === d.unit_id ? null : d.unit_id)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={d.assignee_id ?? ""}
                      onChange={e => updateDraft(d.unit_id, { assignee_id: e.target.value ? Number(e.target.value) : null })}
                      className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
                    >
                      <option value="">미배정</option>
                      {members.map(m => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                      ))}
                    </select>
                    {d.assignee_id == null && d.hold_explanation && (
                      <p className="text-[11px] text-amber-500 mt-1">{d.hold_explanation}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {d.score != null ? (
                      <span className="text-[11px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full">{d.score}</span>
                    ) : <span className="text-xs text-muted-foreground">-</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <input type="date" value={d.start_date} onChange={e => updateDraft(d.unit_id, { start_date: e.target.value })}
                        className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40" />
                      <span className="text-muted-foreground">~</span>
                      <input type="date" value={d.end_date} onChange={e => updateDraft(d.unit_id, { end_date: e.target.value })}
                        className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40" />
                    </div>
                  </td>
                </tr>
                {expandedUnitId === d.unit_id && (
                  <ReasonRow techFit={d.tech_fit} workloadFit={d.workload_fit} experienceFit={d.experience_fit} scheduleReason={d.schedule_reason} />
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end gap-3">
        <button
          onClick={onCancel}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors"
        >
          취소
        </button>
        <button
          onClick={onConfirm}
          disabled={confirming || !hasAnyAssignee}
          title={!hasAnyAssignee ? "최소 1건 이상 담당자를 지정해야 확정할 수 있습니다." : undefined}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
        >
          {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
          배분 확정
        </button>
      </div>
      {!hasAnyAssignee && (
        <p className="text-xs text-amber-500 text-right -mt-2">담당자가 배정된 업무가 없습니다. 최소 1건 이상 담당자를 지정해주세요.</p>
      )}
    </div>
  );
}

// 이미 확정(TaskAssignment로 저장)된 목록 — 일반 사용자는 읽기 전용, PM은 담당자 드롭다운으로
// 재배정할 수 있다(기존 PATCH /api/tasks/assignments/{id}/ 재사용).
function TaskAssignmentList({
  tasks, members, isPM, reassigningTaskId, onReassign,
}: {
  tasks: TaskAssignmentDto[]; members: Member[]; isPM: boolean;
  reassigningTaskId: number | null;
  onReassign: (taskId: number, assigneeId: number) => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // 드롭박스를 바꾸는 즉시 저장되면 실수로 잘못 바꾸기 쉽다는 피드백 — 이 기능 전체가
  // "제안 → 확정" 패턴이니 재배정도 똑같이, 고르기만 하면 우선 화면에만 반영(staged)되고
  // 옆의 "확정" 버튼을 눌러야 실제로 PATCH가 나간다.
  const [pendingReassign, setPendingReassign] = useState<Record<number, number>>({});

  const ganttItems: GanttItem[] = tasks
    .filter(t => t.start_date && t.end_date)
    .map(t => ({ id: String(t.id), title: t.title, assigneeName: t.assigned_user_name, start: t.start_date!, end: t.end_date! }));

  return (
    <div className="space-y-4">
      <CollapsibleSection title="예상 필요 인원">
        <HeadcountSummary assigneeIds={tasks.map(t => t.assigned_user)} members={members} />
      </CollapsibleSection>
      <CollapsibleSection title="업무 일정">
        <GanttChart items={ganttItems} />
      </CollapsibleSection>
      <div className="border border-border rounded-xl overflow-hidden overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-4 py-3 font-bold">업무명 / 배정 근거</th>
              <th className="px-4 py-3 font-bold w-44">담당자</th>
              <th className="px-4 py-3 font-bold w-40">일정</th>
              <th className="px-4 py-3 font-bold w-28">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {tasks.map(t => (
              <Fragment key={t.id}>
                <tr className="align-top">
                  <td className="px-4 py-3">
                    <TaskTitleCell
                      title={t.title}
                      estimatedHours={t.estimated_hours}
                      techFit={t.assignment_reason}
                      expanded={expandedId === t.id}
                      onToggleExpand={() => setExpandedId(v => v === t.id ? null : t.id)}
                    />
                    {t.epic_title && <p className="text-xs text-muted-foreground mt-0.5 pl-4">{t.epic_no} · {t.epic_title}</p>}
                  </td>
                  <td className="px-4 py-3">
                    {/* 배분 확정(APPROVED)된 업무는 담당자 드롭박스 자체를 비활성화한다 —
                        "확정된 이후에는 담당자 변경이 안 되도록" 해야 한다는 사용자 지적으로
                        수정(이전엔 APPROVED 상태에서도 재배정 드롭박스를 열어뒀었다). 확정
                        전 상태(PENDING_APPROVAL — 자동배정 등 다른 경로로 만들어진 업무)만
                        드롭박스로 담당자를 바꿀 수 있고, 확정된 뒤엔 읽기 전용으로 보여준다. */}
                    {isPM && t.status_info?.code_id !== "APPROVED" ? (
                      <div className="flex items-center gap-1">
                        <select
                          value={pendingReassign[t.id] ?? t.assigned_user}
                          onChange={e => {
                            const next = Number(e.target.value);
                            setPendingReassign(prev => {
                              if (next === t.assigned_user) {
                                const { [t.id]: _omit, ...rest } = prev;
                                return rest;
                              }
                              return { ...prev, [t.id]: next };
                            });
                          }}
                          disabled={reassigningTaskId === t.id}
                          className={cn(
                            "w-full border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50",
                            pendingReassign[t.id] != null
                              ? "bg-amber-500/10 border-amber-500/40"
                              : "bg-black/5 dark:bg-white/5 border-border"
                          )}
                        >
                          {members.map(m => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                          ))}
                        </select>
                        {pendingReassign[t.id] != null && (
                          <>
                            <button
                              type="button"
                              title="담당자 변경 확정"
                              disabled={reassigningTaskId === t.id}
                              onClick={() => {
                                const newId = pendingReassign[t.id];
                                onReassign(t.id, newId);
                                setPendingReassign(prev => { const { [t.id]: _omit, ...rest } = prev; return rest; });
                              }}
                              className="shrink-0 p-1.5 rounded-lg text-emerald-500 hover:bg-emerald-500/10 disabled:opacity-50"
                            >
                              {reassigningTaskId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                            </button>
                            <button
                              type="button"
                              title="취소"
                              disabled={reassigningTaskId === t.id}
                              onClick={() => setPendingReassign(prev => { const { [t.id]: _omit, ...rest } = prev; return rest; })}
                              className="shrink-0 p-1.5 rounded-lg text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        {isPM ? <Lock className="w-3.5 h-3.5 text-muted-foreground/50" /> : <UserIcon className="w-3.5 h-3.5 text-muted-foreground" />}
                        <span className="text-xs font-medium">{t.assigned_user_name}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {t.start_date && t.end_date ? (
                      <span className="flex flex-col gap-0.5">
                        <span className="flex items-center gap-1"><CalendarIcon className="w-3 h-3 shrink-0" /> {new Date(t.start_date).toLocaleDateString()}</span>
                        <span className="pl-4">~ {new Date(t.end_date).toLocaleDateString()}</span>
                      </span>
                    ) : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {/* 이 화면에서 확정된 업무는 APPROVED로 바로 시작한다(PM 본인이 확정하는
                        액션이라 "확정 = 이미 승인됨" — 위 담당자 드롭박스 조건 주석 참고).
                        PENDING_APPROVAL은 다른 배정 경로(자동배정 등)로 만들어진 업무에만
                        남아있을 수 있어 그 경우에 대비해 문구만 유지한다. */}
                    <span className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold",
                      t.status_info?.code_id === "APPROVED" ? "bg-emerald-500/10 text-emerald-500" : "bg-orange-500/10 text-orange-500"
                    )}>
                      {t.status_info?.code_id === "PENDING_APPROVAL"
                        ? "배분완료 · PM 승인 대기"
                        : t.status_info?.code_id === "APPROVED"
                        ? "배분 확정됨"
                        : t.status_info?.code_name ?? "미지정"}
                    </span>
                  </td>
                </tr>
                {expandedId === t.id && t.assignment_reason && (
                  <ReasonRow
                    techFit={t.assignment_reason.split(" / ")[0] ?? null}
                    workloadFit={t.assignment_reason.split(" / ")[1] ?? null}
                    experienceFit={t.assignment_reason.split(" / ")[2] ?? null}
                  />
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// "예상 필요 인원" 박스 / 업무 일정(Gantt) 공통으로 쓰는 접었다 펼 수 있는 섹션 — 버튼이
// 아니라 제목 자체를 클릭하게(사용자 요청) 만들고, 다른 화면의 펼침형 행(TaskTitleCell 등)과
// 동일하게 ChevronDown이 접힌 상태에서 -90도 회전하는 방식으로 통일한다.
function CollapsibleSection({
  title, defaultOpen = true, children,
}: {
  title: string; defaultOpen?: boolean; children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="space-y-2">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-sm font-bold hover:text-primary transition-colors"
      >
        <ChevronDown className={cn("w-4 h-4 transition-transform shrink-0", !open && "-rotate-90")} />
        {title}
      </button>
      {open && children}
    </div>
  );
}

// SpecDocument.evidence_data(JSON 문자열)를 ProposalTemplate의 섹션별 근거 prop 형태로
// 정규화한다. 백엔드가 어느 명명 규칙으로 저장하든(스네이크케이스 원본 필드명이든, 프론트와
// 동일한 카멜케이스든) 받아들이도록 두 가지 키 형태를 모두 매핑한다 — 포맷이 확정되면
// 필요 없는 쪽은 정리해도 된다.
const EVIDENCE_KEY_ALIASES: Record<string, keyof ProposalEvidence> = {
  overview: "projectOverview", projectOverview: "projectOverview",
  problem_definition: "problemDefinition", problemDefinition: "problemDefinition",
  goals: "projectGoals", projectGoals: "projectGoals",
  target_users: "target", target: "target",
  key_features: "features", features: "features",
  tech_stack: "techStackConstraints", techStackConstraints: "techStackConstraints",
  final_decisions: "finalDecisions", finalDecisions: "finalDecisions",
};

function parseProposalEvidence(raw: string | null): ProposalEvidence {
  if (!raw || !raw.trim()) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const result: ProposalEvidence = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const mappedKey = EVIDENCE_KEY_ALIASES[key];
      if (mappedKey && value != null && String(value).trim()) {
        result[mappedKey] = String(value);
      }
    }
    return result;
  } catch {
    return {};
  }
}

// 업무 목록에서 담당자(중복 제거) 기준으로 직무별 인원수를 집계 — 업무 자체엔 직무 필드가
// 없어서 담당자 계정의 job_role_code로 대신한다.
function HeadcountSummary({ assigneeIds, members }: { assigneeIds: (number | null | undefined)[]; members: Member[] }) {
  const uniqueIds = Array.from(new Set(assigneeIds.filter((id): id is number => id != null)));
  if (uniqueIds.length === 0) return null;

  const counts = new Map<string, number>();
  uniqueIds.forEach(id => {
    const label = roleLabelOf(members.find(m => m.id === id)?.jobRoleCode ?? null);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  });
  // "미분류"는 항상 마지막에 오도록 정렬
  const entries = Array.from(counts.entries()).sort((a, b) =>
    a[0] === "미분류" ? 1 : b[0] === "미분류" ? -1 : 0
  );

  return (
    <div className="border border-border rounded-xl p-4 bg-black/[0.02] dark:bg-white/[0.02]">
      <p className="text-sm font-semibold">예상 필요 인원: 총 {uniqueIds.length}명</p>
      <p className="text-xs text-muted-foreground mt-1">
        {entries.map(([label, count]) => `${label} ${count}`).join(" · ")}
      </p>
    </div>
  );
}

// 담당자별로 업무 막대를 타임라인 위에 배치하는 가벼운 간트 차트(heyzzabi2 GanttChart를
// 그대로 이식, 필드명만 이 파일의 GanttItem에 맞춤). 하루=한 칸인 날짜 그리드라 기간이
// 짧아도(며칠) 눈금이 중복되지 않는다.
function GanttChart({ items }: { items: GanttItem[] }) {
  if (items.length === 0) return null;

  const toLocalMidnight = (iso: string) => {
    const d = new Date(iso);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  };
  const DAY_MS = 86400000;

  const starts = items.map(i => toLocalMidnight(i.start));
  const ends = items.map(i => toLocalMidnight(i.end));
  const rangeStartMs = Math.min(...starts);
  const rangeEndMs = Math.max(...ends);
  const dayCount = Math.max(1, Math.round((rangeEndMs - rangeStartMs) / DAY_MS) + 1);
  const days = Array.from({ length: dayCount }, (_, i) => new Date(rangeStartMs + i * DAY_MS));
  const dayIndexOf = (iso: string) => Math.min(dayCount - 1, Math.max(0, Math.round((toLocalMidnight(iso) - rangeStartMs) / DAY_MS)));
  const fmtDate = (d: Date) => d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  const fmtWeekday = (d: Date) => d.toLocaleDateString("ko-KR", { weekday: "short" });
  const todayIndex = Math.round((toLocalMidnight(new Date().toISOString()) - rangeStartMs) / DAY_MS);

  const byAssignee = new Map<string, GanttItem[]>();
  items.forEach(i => {
    if (!byAssignee.has(i.assigneeName)) byAssignee.set(i.assigneeName, []);
    byAssignee.get(i.assigneeName)!.push(i);
  });

  // 2026-09-11: 담당자별로 묶고, 그룹 안에서는 시작일 오름차순으로 정렬한다
  // (입력 순서 = 배정 순서라 그대로 두면 날짜순이 아니었다). 그룹 자체도 그
  // 담당자의 첫 시작일 기준으로 정렬해 위에서 아래로 시간 순으로 읽히게 한다.
  const groups = Array.from(byAssignee.entries())
    .map(([name, personItems]) => {
      const sorted = [...personItems].sort((a, b) => toLocalMidnight(a.start) - toLocalMidnight(b.start));
      return { name, items: sorted, firstStart: toLocalMidnight(sorted[0].start) };
    })
    .sort((a, b) => a.firstStart - b.firstStart);

  const rows: { label: string | null; item: GanttItem }[] = [];
  groups.forEach(({ name, items: personItems }) => {
    personItems.forEach((item, idx) => rows.push({ label: idx === 0 ? name : null, item }));
  });

  const dayGridStyle = { gridTemplateColumns: `repeat(${dayCount}, minmax(52px, 1fr))` };
  const dayColClass = (i: number) =>
    cn(
      "border-l border-dashed",
      i === todayIndex ? "border-primary/40" : "border-border",
      i === dayCount - 1 && "border-r border-border"
    );

  return (
    <div className="border border-border rounded-xl p-4 overflow-x-auto">
      <div style={{ minWidth: `${96 + dayCount * 52}px` }}>
        <div className="grid gap-y-2" style={{ gridTemplateColumns: `96px 1fr` }}>
          <div />
          <div className="grid" style={dayGridStyle}>
            {days.map((d, i) => (
              <div key={i} className={cn("text-center pb-1.5", dayColClass(i))}>
                <p className={cn("text-[10px] font-semibold", i === todayIndex ? "text-primary" : "text-muted-foreground")}>{fmtDate(d)}</p>
                <p className="text-[9px] text-muted-foreground/60">{fmtWeekday(d)}</p>
              </div>
            ))}
          </div>

          {rows.map(({ label, item }) => {
            const s = dayIndexOf(item.start);
            const e = dayIndexOf(item.end);
            const left = (s / dayCount) * 100;
            const width = ((e - s + 1) / dayCount) * 100;
            const narrow = width < 14;
            return (
              <Fragment key={item.id}>
                <p className="text-xs font-bold text-muted-foreground flex items-center gap-1 truncate pt-1">
                  {label && (<><UserIcon className="w-3 h-3 shrink-0" /><span className="truncate">{label}</span></>)}
                </p>
                <div className="relative h-6">
                  <div className="absolute inset-0 grid" style={dayGridStyle}>
                    {days.map((_, i) => <div key={i} className={dayColClass(i)} />)}
                  </div>
                  <div
                    title={`${item.title} · ${fmtDate(days[s])} ~ ${fmtDate(days[e])}`}
                    className="absolute top-0 h-full rounded-md flex items-center px-2 bg-primary/80 hover:bg-primary transition-colors overflow-hidden"
                    style={{ left: `${left}%`, width: `${width}%` }}
                  >
                    {!narrow && <span className="text-[10px] font-semibold text-primary-foreground truncate">{item.title}</span>}
                  </div>
                  {narrow && (
                    <span
                      className="absolute top-1/2 -translate-y-1/2 text-[10px] font-medium text-foreground whitespace-nowrap pointer-events-none"
                      style={{ left: `calc(${left}% + ${width}% + 6px)` }}
                    >
                      {item.title}
                    </span>
                  )}
                </div>
              </Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function RequirementSection({
  spec, reqDef, isPM, canGenerate, busy, onCreate, onExtract, onAddItem, onUpdateItem, onDeleteItem, onStatusChange,
  onGenerateTasks, generatingTasks, onRejectClick, tasksAlreadyAssigned,
}: {
  spec: SpecDto; reqDef: ReqDefDto | null; isPM: boolean;
  // 기획서 탭과 동일한 규칙 — 이 문서(회의록)를 시작한 작성자 본인만 요구사항정의서를
  // 생성/수정/삭제/검토요청할 수 있다. 예전엔 isPM만 봐서, PM이 아니기만 하면 다른
  // 사람이 시작한 문서의 요구사항정의서도 마음대로 건드릴 수 있는 문제가 있었다.
  canGenerate: boolean;
  busy: string | null;
  onCreate: () => void;
  onExtract: (specId: number, reqDefId: number) => void;
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string; order: number; priority_code: string | null }) => void;
  onUpdateItem: (reqDefId: number, itemId: number, patch: { req_name: string; description: string; priority_code?: string | null }) => void;
  onDeleteItem: (reqDefId: number, itemId: number) => void;
  // REJECTED는 사유 입력 모달(onRejectClick)을 거쳐서만 일어난다 — 상태만 바로 바꾸는
  // 경로를 남겨두면 사유 없이 반려하는 길이 다시 생긴다.
  onStatusChange: (statusCode: "PENDING_REVIEW" | "APPROVED") => void;
  onGenerateTasks: () => void;
  generatingTasks: boolean;
  onRejectClick: () => void;
  // 이미 배분을 확정한 뒤에는 "업무 배분 실행" 버튼을 완전히 숨긴다 — PM이 요구사항정의서
  // 탭으로 돌아왔을 때 버튼이 그대로 남아있으면 실수로 다시 눌러 기존 배정을 통째로
  // 덮어쓸 위험이 있다(사용자 요청 — 재배분이 필요하면 업무배분 탭에서 별도로 처리).
  tasksAlreadyAssigned: boolean;
}) {
  // 하단에 고정된 "항목 직접 추가" 버튼 대신, 표의 행과 행 사이에 있는 + 버튼을 눌러 그
  // 자리에 바로 추가 폼이 펼쳐지도록 바꿨다(사용자 요청). null이면 어디에도 안 열려있고,
  // "start"면 첫 행 위, 숫자면 그 항목 바로 아래에 폼이 펼쳐진다. RequirementItem.order
  // (실수)에 이웃 두 항목의 중간값을 매겨서 실제로 그 위치에 저장된다.
  const [addFormAt, setAddFormAt] = useState<number | "start" | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  // 코드(REQ-01 등)는 삽입 위치의 앞 항목 코드를 보고 자동으로 다음 번호를 매긴다 —
  // 사용자가 직접 입력하지 않는다(사용자 요청, incrementCode 참고).
  const [newPriority, setNewPriority] = useState("");
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editPriority, setEditPriority] = useState("");

  // 같은 그룹 안에는 행 사이 +버튼이 안 뜨니(위 groupOf 참고), 기존 그룹 안에 항목을 더
  // 추가하려면 이 하단 버튼이 필요하다(사용자 요청 — "추가하기 버튼 살려줘"). 코드를
  // 직접 입력하는 대신 분류(기능/비기능)와 그룹을 고르면 그 안에서 다음 번호가 자동으로
  // 매겨진다(예: FR-01에 001~004가 있으면 005).
  const [bottomAddOpen, setBottomAddOpen] = useState(false);
  const [bottomCategory, setBottomCategory] = useState<"FR" | "NFR">("FR");
  const [bottomGroup, setBottomGroup] = useState<string>("__new__");
  const [bottomName, setBottomName] = useState("");
  const [bottomDesc, setBottomDesc] = useState("");
  const [bottomPriority, setBottomPriority] = useState("");

  // 엑셀처럼 컬럼 헤더를 눌러 정렬(코드/우선순위) — null이면 원래 순서(순번=order 기준).
  // 정렬 중에는 화면 순서가 실제 저장 순서(order)와 달라지므로 그룹 경계 판단이나 행
  // 사이 +버튼 삽입이 의미 없어져서 정렬 중엔 숨긴다(아래 렌더링 참고).
  const [sortColumn, setSortColumn] = useState<"code" | "priority" | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const toggleSort = (col: "code" | "priority") => {
    if (sortColumn !== col) { setSortColumn(col); setSortDir("asc"); }
    else if (sortDir === "asc") setSortDir("desc");
    else { setSortColumn(null); setSortDir("asc"); }
  };

  const creating = busy === `${spec.id}-create-reqdef`;
  const extracting = reqDef && busy === `reqdef-${reqDef.id}-extract`;
  const addingItem = reqDef && busy === `reqdef-${reqDef.id}-additem`;
  const reqStatus = reqDef?.status_info?.code_id ?? null;
  const approving = reqDef && busy === `reqdef-${reqDef.id}-approved`;
  const rejecting = reqDef && busy === `reqdef-${reqDef.id}-rejected`;
  const submittingReview = reqDef && busy === `reqdef-${reqDef.id}-pending_review`;
  // 검토요청(PENDING_REVIEW) ~ 승인(APPROVED) 사이에는 기획서와 마찬가지로 항목을 잠근다 —
  // 이미 검토에 들어간 내용이 뒤에서 바뀌면 안 되기 때문. 백엔드(requirements/views.py의
  // LOCKED_REQDEF_STATUSES + RequirementItemViewSet.create()/RequirementItemDetailView.
  // _check_not_locked())도 생성·수정·삭제를 동일하게 막고 있어 API 직접 호출로 우회할 수
  // 없다 — 이건 화면에서 버튼/입력을 미리 비활성화해 사용자 경험을 매끄럽게 하는 역할.
  const itemsLocked = reqStatus === "APPROVED" || reqStatus === "PENDING_REVIEW";

  // 기획서 탭의 PDF/PPTX 다운로드와 동일한 자리 — 요구사항정의서는 표 형태라 PDF 대신
  // 엑셀(원본 양식과 같은 컬럼)과 PPTX(표 슬라이드)로 내보낸다. reqDef는 위에서
  // null 체크 전이라 이 시점엔 아직 null일 수 있어 각 핸들러에서 다시 확인한다.
  const handleReqSpecExcel = async () => {
    if (!reqDef) return;
    await exportReqSpecExcel(reqDefToReqSpecDoc(reqDef), spec.title);
  };
  const handleReqSpecPptx = async () => {
    if (!reqDef) return;
    await exportReqSpecPptx(reqDefToReqSpecDoc(reqDef), spec.title);
  };

  if (!reqDef) {
    return (
      <div className="border-t border-border pt-5 mt-2">
        <h3 className="font-bold text-sm mb-2">요구사항 정의서</h3>
        {canGenerate && !isPM ? (
          <button
            onClick={onCreate}
            disabled={creating}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
            요구사항 정의서 생성
          </button>
        ) : (
          <p className="text-sm text-muted-foreground">
            {!canGenerate ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 생성할 수 있습니다." : "아직 요구사항 정의서가 생성되지 않았습니다."}
          </p>
        )}
      </div>
    );
  }

  return (
    <fieldset disabled={busy !== null} aria-busy={!!extracting} className="min-w-0 border-t border-border pt-5 mt-2 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            {/* reqDef.title은 "{회의록 제목} - 요구사항 정의서" 형태라 위쪽 페이지 헤더의
                문서 제목과 거의 그대로 겹쳐서 중복으로 보인다는 피드백 — 여기선 고정
                라벨만 두고 제목 반복은 없앤다. */}
            <h3 className="font-bold text-sm">요구사항 정의서</h3>
            <span className="text-xs font-mono font-normal text-muted-foreground/70">요구사항정의서 번호 {reqDef.id}</span>
            {/* 전용 승인/반려 엔드포인트가 없어서(기획서와 달리) 상태 배지 스타일도 로컬로
                따로 둔다 — 문서 전체의 STATUS_META를 그대로 쓰면 REQSPEC_STATUS 그룹의
                실제 값(PENDING_REVIEW 등)과 안 맞는 경우가 생길 수 있어 최소한만 표시. */}
            {reqStatus && (
              <span className={cn(
                "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold",
                reqStatus === "APPROVED" ? "bg-emerald-500/10 text-emerald-500"
                  : reqStatus === "REJECTED" ? "bg-red-500/10 text-red-500"
                  : "bg-orange-500/10 text-orange-500"
              )}>
                {reqDef.status_info?.code_name ?? reqStatus}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">항목 {reqDef.items.length}건</p>
          {/* 기획서 반려 사유 박스(review_comment)와 동일한 자리·스타일 — reject_reason
              필드 추가로 이제 요구사항정의서도 반려 사유를 남길 수 있다. */}
          {reqStatus === "REJECTED" && reqDef.reject_reason && (
            <div className="flex items-start gap-2 mt-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 max-w-xl">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div><span className="font-semibold">반려 사유:</span> {reqDef.reject_reason}</div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {reqStatus === "APPROVED" && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
              <Lock className="w-3 h-3" /> 승인되어 항목이 잠겼습니다
            </span>
          )}
          {/* heyzzabi2와 동일 — 요구사항정의서가 승인되면 PM이 다음 단계(업무분배)로
              넘어갈 업무를 AI로 자동 추출·배정할 수 있다. 이미 확정된 배정이 있으면
              버튼 자체를 숨긴다(사용자 요청) — 재배분은 업무배분 탭에서만. */}
          {reqStatus === "APPROVED" && isPM && tasksAlreadyAssigned && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
              <CheckCircle2 className="w-3 h-3" /> 업무 배분 완료 — 업무배분 탭에서 확인
            </span>
          )}
          {reqStatus === "APPROVED" && isPM && !tasksAlreadyAssigned && (
            <button
              onClick={onGenerateTasks}
              disabled={generatingTasks}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 disabled:opacity-50"
            >
              {generatingTasks ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5" />}
              업무 배분 실행
            </button>
          )}
          {reqStatus === "PENDING_REVIEW" && !isPM && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
              <Clock className="w-3 h-3" /> 검토 요청됨 · 승인 대기 중
            </span>
          )}
          {/* 검토요청은 하단으로 옮겼다(기획서 탭과 통일 — 승인/반려만 상단, 검토요청/
              항목추가는 하단). 아래 표 밑 액션바 참고. */}
          {/* 요구사항정의서 승인/반려 — 검토요청(PENDING_REVIEW) 상태일 때만 PM에게 노출된다.
              반려는 사유 입력 모달(onRejectClick, reject_reason 필드)을 거친다 —
              기획서 반려와 동일한 방식(팀 전달 목록에 있던 항목, 추가 완료). */}
          {isPM && reqStatus === "PENDING_REVIEW" && (
            <>
              <button
                onClick={onRejectClick}
                disabled={!!rejecting || !!approving}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold hover:bg-red-500/20 disabled:opacity-50"
              >
                {rejecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
                반려
              </button>
              <button
                onClick={() => onStatusChange("APPROVED")}
                disabled={!!approving || !!rejecting}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500 text-white text-xs font-semibold hover:bg-emerald-600 disabled:opacity-50"
              >
                {approving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                승인
              </button>
            </>
          )}
        </div>
      </div>

      {/* 항목 삽입 위치 계산 — order는 정수가 아니라 실수라, 두 이웃 항목의 order 중간값을
          매기면 다른 항목들의 order를 하나도 안 건드리고 그 사이에 끼워넣을 수 있다.
          "start"는 첫 항목 앞, 항목 id는 그 항목 바로 다음 자리를 뜻한다. */}
      {(() => {
        const insertOrderAt = (pos: number | "start"): number => {
          const items = reqDef.items;
          if (items.length === 0) return 1;
          if (pos === "start") return items[0].order - 1;
          const idx = items.findIndex(it => it.id === pos);
          if (idx === -1 || idx === items.length - 1) return items[items.length - 1].order + 1;
          return (items[idx].order + items[idx + 1].order) / 2;
        };
        // 삽입 위치의 "앞 항목" 코드를 기준으로 다음 번호를 자동으로 매긴다(사용자 요청 —
        // 직접 코드를 입력하지 않아도 FR-01-003 다음에 넣으면 FR-01-004가 되도록).
        // 맨 앞(start)에 넣을 항목이 없으면 첫 항목 코드를 그대로 이어받는다.
        const autoCodeAt = (pos: number | "start"): string => {
          const items = reqDef.items;
          if (items.length === 0) return "FR-01-001";
          if (pos === "start") return items[0].req_code;
          const idx = items.findIndex(it => it.id === pos);
          const base = idx === -1 ? items[items.length - 1] : items[idx];
          return incrementCode(base.req_code);
        };
        const openAddForm = (pos: number | "start") => {
          setAddFormAt(pos);
          setNewName(""); setNewDesc(""); setNewPriority("");
        };
        const submitAddForm = (pos: number | "start") => {
          if (!newName.trim()) return;
          onAddItem(reqDef.id, {
            req_code: autoCodeAt(pos),
            req_name: newName.trim(),
            description: newDesc.trim(),
            order: insertOrderAt(pos),
            priority_code: newPriority || null,
          });
          setAddFormAt(null);
        };
        const addFormFields = (pos: number | "start") => (
          <>
            <div className="grid grid-cols-[1fr_120px] gap-2">
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="요구사항명"
                className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              <select
                value={newPriority}
                onChange={e => setNewPriority(e.target.value)}
                className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="">우선순위</option>
                {PRIORITY_OPTIONS.map(p => (
                  <option key={p.code_id} value={p.code_id}>{p.label}</option>
                ))}
              </select>
            </div>
            <textarea
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              placeholder="상세 내용"
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm resize-none h-20 focus:outline-none focus:ring-2 focus:ring-primary/40 mt-2"
            />
            <div className="flex items-center justify-between mt-2">
              <p className="text-[11px] text-muted-foreground/70 font-mono">코드 {autoCodeAt(pos)} (자동)</p>
              <div className="flex justify-end gap-2">
                <button onClick={() => setAddFormAt(null)} className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg">취소</button>
                <button
                  onClick={() => submitAddForm(pos)}
                  disabled={!newName.trim() || !!addingItem}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
                >
                  {addingItem ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  추가
                </button>
              </div>
            </div>
          </>
        );
        const renderDivider = (pos: number | "start") => (
          <tr className="group h-3">
            <td colSpan={6} className="p-0 relative">
              <div className="absolute inset-x-4 top-1/2 -translate-y-1/2 border-t border-dashed border-transparent group-hover:border-border/60 transition-colors" />
              <button
                type="button"
                onClick={() => openAddForm(pos)}
                title="이 위치에 항목 추가"
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-5 rounded-full border border-border bg-background flex items-center justify-center text-muted-foreground opacity-0 group-hover:opacity-100 hover:!opacity-100 hover:text-primary hover:border-primary transition-opacity z-10"
              >
                <Plus className="w-3 h-3" />
              </button>
            </td>
          </tr>
        );
        const renderAddFormRow = (pos: number | "start") => (
          <tr>
            <td colSpan={6} className="px-4 py-3 bg-black/5 dark:bg-white/5">
              {addFormFields(pos)}
            </td>
          </tr>
        );

        // 하단 "항목 직접 추가" 버튼 — 같은 그룹 안에는 행 사이 +버튼이 없어서, 기존 그룹에
        // 항목을 더 넣고 싶을 때 쓴다(사용자 요청). 분류(기능/비기능)+그룹을 고르면 그
        // 그룹의 다음 번호가 자동으로 매겨진다(코드 직접 입력 없음).
        const groupsFor = (prefix: "FR" | "NFR"): string[] => {
          const set = new Set<string>();
          reqDef.items.forEach(it => {
            const p = parseCode(it.req_code);
            if (p && p.prefix === prefix) set.add(p.group);
          });
          return Array.from(set).sort();
        };
        const nextSeqInGroup = (prefix: "FR" | "NFR", group: string): string => {
          const seqs = reqDef.items
            .map(it => parseCode(it.req_code))
            .filter((p): p is NonNullable<typeof p> => !!p && p.prefix === prefix && p.group === group)
            .map(p => parseInt(p.seq, 10));
          const max = seqs.length ? Math.max(...seqs) : 0;
          return String(max + 1).padStart(3, "0");
        };
        const nextGroupNumber = (prefix: "FR" | "NFR"): string => {
          const nums = groupsFor(prefix).map(g => parseInt(g, 10));
          const max = nums.length ? Math.max(...nums) : 0;
          return String(max + 1).padStart(2, "0");
        };
        const bottomCode = bottomGroup === "__new__"
          ? `${bottomCategory}-${nextGroupNumber(bottomCategory)}-001`
          : `${bottomCategory}-${bottomGroup}-${nextSeqInGroup(bottomCategory, bottomGroup)}`;
        const bottomOrder = (): number => {
          const items = reqDef.items;
          if (items.length === 0) return 1;
          if (bottomGroup === "__new__") return items[items.length - 1].order + 1;
          let lastIdx = -1;
          items.forEach((it, i) => {
            const p = parseCode(it.req_code);
            if (p && p.prefix === bottomCategory && p.group === bottomGroup) lastIdx = i;
          });
          if (lastIdx === -1) return items[items.length - 1].order + 1;
          if (lastIdx === items.length - 1) return items[lastIdx].order + 1;
          return (items[lastIdx].order + items[lastIdx + 1].order) / 2;
        };
        const openBottomAdd = () => {
          setBottomAddOpen(true);
          const groups = groupsFor(bottomCategory);
          setBottomGroup(groups[0] ?? "__new__");
          setBottomName(""); setBottomDesc(""); setBottomPriority("");
        };
        const submitBottomAdd = () => {
          if (!bottomName.trim()) return;
          onAddItem(reqDef.id, {
            req_code: bottomCode,
            req_name: bottomName.trim(),
            description: bottomDesc.trim(),
            order: bottomOrder(),
            priority_code: bottomPriority || null,
          });
          setBottomAddOpen(false);
        };

        // 엑셀처럼 코드/우선순위 헤더를 눌러 정렬 — 정렬 중엔 화면 순서가 실제 order와
        // 달라지므로 그룹 경계/삽입 위치 계산(+버튼)은 원래 순서(reqDef.items) 기준 그대로
        // 두고, 화면에 뿌리는 목록만 displayItems로 바꾼다.
        const displayItems = !sortColumn ? reqDef.items : [...reqDef.items].sort((a, b) => {
          let cmp = 0;
          if (sortColumn === "code") cmp = a.req_code.localeCompare(b.req_code);
          else if (sortColumn === "priority") {
            const wa = PRIORITY_SORT_WEIGHT[a.priority_info?.code_name ?? ""] ?? 0;
            const wb = PRIORITY_SORT_WEIGHT[b.priority_info?.code_name ?? ""] ?? 0;
            cmp = wa - wb;
          }
          return sortDir === "asc" ? cmp : -cmp;
        });
        const sortArrow = (col: "code" | "priority") => sortColumn === col ? (sortDir === "asc" ? "▲" : "▼") : "";

        if (reqDef.items.length === 0) {
          return (
            <div className="py-4 text-center space-y-3">
              <p className="text-sm text-muted-foreground">아직 요구사항 항목이 없습니다.</p>
              {!isPM && canGenerate && !itemsLocked && (
                addFormAt === "start" ? (
                  <div className="border border-border rounded-xl p-4 text-left max-w-md mx-auto">{addFormFields("start")}</div>
                ) : (
                  <button
                    onClick={() => openAddForm("start")}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                  >
                    <Plus className="w-3.5 h-3.5" /> 항목 직접 추가
                  </button>
                )
              )}
            </div>
          );
        }

        return (
        <>
        <div className="border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
              <tr>
                <th className="px-4 py-2.5 font-bold w-14">순번</th>
                <th className="px-4 py-2.5 font-bold w-24">분류</th>
                <th className="px-4 py-2.5 font-bold w-28">
                  <button type="button" onClick={() => toggleSort("code")} className="flex items-center gap-1 hover:text-foreground">
                    코드 <span className="text-primary">{sortArrow("code")}</span>
                  </button>
                </th>
                <th className="px-4 py-2.5 font-bold">요구사항명</th>
                <th className="px-4 py-2.5 font-bold w-24">
                  <button type="button" onClick={() => toggleSort("priority")} className="flex items-center gap-1 hover:text-foreground">
                    우선순위 <span className="text-primary">{sortArrow("priority")}</span>
                  </button>
                </th>
                {!isPM && canGenerate && !itemsLocked && <th className="px-4 py-2.5 font-bold w-20 text-right">관리</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {!sortColumn && !isPM && canGenerate && !itemsLocked && (
                addFormAt === "start" ? renderAddFormRow("start") : renderDivider("start")
              )}
              {displayItems.map((item, index) => {
                const isEditing = editingItemId === item.id;
                const deleting = busy === `reqitem-${item.id}-delete`;
                const updating = busy === `reqitem-${item.id}-update`;
                return (
                  <Fragment key={item.id}>
                  <tr>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground align-middle">{index + 1}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground align-middle">
                      {/* req_code 접두사(FR/NFR)로 기능·비기능을 구분한다 — category 필드는
                          도메인 세부분류(재고 관리, 보안성 등)라 기능/비기능 여부와는 다르다. */}
                      {item.req_code?.startsWith("NFR") ? "비기능" : item.req_code?.startsWith("FR") ? "기능" : "-"}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground align-middle whitespace-nowrap">{item.req_code}</td>
                    <td className="px-4 py-2.5 align-top">
                      {isEditing ? (
                        <div className="space-y-1.5">
                          <input
                            value={editName}
                            onChange={e => setEditName(e.target.value)}
                            className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40"
                          />
                          <textarea
                            value={editDesc}
                            onChange={e => setEditDesc(e.target.value)}
                            className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs resize-none h-16 focus:outline-none focus:ring-2 focus:ring-primary/40"
                          />
                        </div>
                      ) : (
                        <>
                          <p className="font-semibold">{item.req_name}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                        </>
                      )}
                    </td>
                    <td className="px-4 py-2.5 align-middle">
                      {/* 설명 아래 회색 텍스트로만 있던 우선순위를 별도 컬럼 + 상/중/하 색
                          배지로 바꿨다(가독성 피드백) — 신호등처럼 급함(상)=빨강,
                          보통(중)=주황, 낮음(하)=회색. 요구사항명만 내용이 길어서 위쪽
                          정렬, 나머지 컬럼(순번/분류/코드/우선순위/관리)은 세로 중앙
                          정렬로 맞췄다(요청). 수정 모드에서는 AI가 생성한 항목이라도
                          드롭박스로 우선순위를 바꿀 수 있다(요청). */}
                      {isEditing ? (
                        <select
                          value={editPriority}
                          onChange={e => setEditPriority(e.target.value)}
                          className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
                        >
                          <option value="">미지정</option>
                          {PRIORITY_OPTIONS.map(p => (
                            <option key={p.code_id} value={p.code_id}>{p.label}</option>
                          ))}
                        </select>
                      ) : (() => {
                        const code = item.priority_info?.code_name ?? "";
                        const label = PRIORITY_LABEL[code];
                        return (
                          <span className={cn(
                            "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold",
                            PRIORITY_BADGE_CLASS[code] ?? "bg-black/5 dark:bg-white/5 text-muted-foreground"
                          )}>
                            {label ?? "미지정"}
                          </span>
                        );
                      })()}
                    </td>
                    {!isPM && canGenerate && !itemsLocked && (
                      <td className="px-4 py-2.5 align-middle">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => setEditingItemId(null)}
                              className="p-1.5 rounded-lg text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5"
                            >
                              취소
                            </button>
                            <button
                              onClick={() => {
                                if (!editName.trim()) return;
                                onUpdateItem(reqDef.id, item.id, { req_name: editName.trim(), description: editDesc.trim(), priority_code: editPriority || null });
                                setEditingItemId(null);
                              }}
                              disabled={!editName.trim() || updating}
                              className="p-1.5 rounded-lg text-primary hover:bg-primary/10 disabled:opacity-50"
                            >
                              {updating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "저장"}
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setEditingItemId(item.id); setEditName(item.req_name); setEditDesc(item.description); setEditPriority(item.priority_info?.code_id ?? ""); }}
                              title="항목 수정"
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => onDeleteItem(reqDef.id, item.id)}
                              disabled={deleting}
                              title="항목 삭제"
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                            >
                              {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                  {/* 같은 그룹(FR-01 등) 안에서는 +버튼을 안 보여준다 — 다음 항목이 없거나
                      (마지막 행) 그룹이 다를 때만 표시. 정렬 중에는 화면 순서와 실제 order가
                      달라서 삽입 위치 계산이 의미 없어지므로 +버튼 자체를 숨긴다. */}
                  {!sortColumn && !isPM && canGenerate && !itemsLocked && (
                    index === reqDef.items.length - 1 || groupOf(item.req_code) !== groupOf(reqDef.items[index + 1].req_code)
                  ) && (
                    addFormAt === item.id ? renderAddFormRow(item.id) : renderDivider(item.id)
                  )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        {!isPM && canGenerate && !itemsLocked && (
          bottomAddOpen ? (
            <div className="border border-border rounded-xl p-4 space-y-2 mt-3">
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={bottomCategory}
                  onChange={e => {
                    const cat = e.target.value as "FR" | "NFR";
                    setBottomCategory(cat);
                    setBottomGroup(groupsFor(cat)[0] ?? "__new__");
                  }}
                  className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="FR">기능 (FR)</option>
                  <option value="NFR">비기능 (NFR)</option>
                </select>
                <select
                  value={bottomGroup}
                  onChange={e => setBottomGroup(e.target.value)}
                  className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  {groupsFor(bottomCategory).map(g => (
                    <option key={g} value={g}>{bottomCategory}-{g} (다음 {nextSeqInGroup(bottomCategory, g)})</option>
                  ))}
                  <option value="__new__">새 그룹 추가 ({bottomCategory}-{nextGroupNumber(bottomCategory)})</option>
                </select>
              </div>
              <div className="grid grid-cols-[1fr_120px] gap-2">
                <input
                  value={bottomName}
                  onChange={e => setBottomName(e.target.value)}
                  placeholder="요구사항명"
                  className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <select
                  value={bottomPriority}
                  onChange={e => setBottomPriority(e.target.value)}
                  className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="">우선순위</option>
                  {PRIORITY_OPTIONS.map(p => (
                    <option key={p.code_id} value={p.code_id}>{p.label}</option>
                  ))}
                </select>
              </div>
              <textarea
                value={bottomDesc}
                onChange={e => setBottomDesc(e.target.value)}
                placeholder="상세 내용"
                className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm resize-none h-20 focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-muted-foreground/70 font-mono">코드 {bottomCode} (자동)</p>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setBottomAddOpen(false)} className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg">취소</button>
                  <button
                    onClick={submitBottomAdd}
                    disabled={!bottomName.trim() || !!addingItem}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
                  >
                    {addingItem ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    추가
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <button
              onClick={openBottomAdd}
              className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
            >
              <Plus className="w-3.5 h-3.5" /> 항목 직접 추가
            </button>
          )
        )}
        {/* 기획서 탭의 하단 액션 줄(flex justify-end items-center gap-3 pt-2 +
            mr-auto 다운로드 그룹)과 구조·클래스를 그대로 맞춘다(사용자 요청 —
            "요구사항정의서 다운로드 버튼도 기획서와 통일"). 요구사항정의서는 표라서
            PDF 대신 엑셀(원본 양식과 같은 컬럼)로, PPTX는 표 슬라이드로 내보낸다.
            상태와 무관하게 항상 노출(초안 단계에서도 팀 공유용으로 뽑아볼 수 있어야 함). */}
        <div className="flex justify-end items-center gap-3 pt-2">
          <div className="flex items-center gap-2 mr-auto">
            <button onClick={handleReqSpecExcel} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <FileSpreadsheet className="w-3.5 h-3.5" /> Excel 다운로드
            </button>
            <button onClick={handleReqSpecPptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <Download className="w-3.5 h-3.5" /> PPTX 다운로드
            </button>
          </div>
          {!isPM && canGenerate && !tasksAlreadyAssigned && (reqStatus === "DRAFT" || reqStatus === "REJECTED" || reqStatus === null) && (
            <button
              onClick={() => {
                if (busy !== null) return;
                if (window.confirm("요구사항정의서를 다시 생성하면 현재 항목(직접 추가·수정한 내용 포함)이 AI 결과로 교체됩니다. 계속하시겠습니까?")) {
                  setEditingItemId(null);
                  setAddFormAt(null);
                  setBottomAddOpen(false);
                  onExtract(spec.id, reqDef.id);
                }
              }}
              disabled={busy !== null}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors disabled:opacity-50"
            >
              {extracting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              {extracting ? "재생성 중…" : "재생성"}
            </button>
          )}
          {/* 검토요청은 하단 우측 — 기획서 탭과 동일한 위치(승인/반려는 상단, 검토요청/
              직접수정 성격의 액션은 하단). reqStatus===null은 REQSPEC_STATUS 도입 전
              기존 데이터라 DRAFT로 간주해 검토요청을 받을 수 있게 한다. */}
          {!isPM && canGenerate && !itemsLocked && (reqStatus === "DRAFT" || reqStatus === "REJECTED" || reqStatus === null) && (
            <button
              onClick={() => onStatusChange("PENDING_REVIEW")}
              disabled={!!submittingReview}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
            >
              {submittingReview ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              검토요청
            </button>
          )}
        </div>
        </>
        );
      })()}
    </fieldset>
  );
}