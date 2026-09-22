"use client";

import { useEffect, useState, useMemo, useRef, Fragment, type Dispatch, type SetStateAction, type ReactNode } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import {
  FileText, Plus, Bot, Loader2, Send, CheckCircle2, XCircle,
  AlertCircle, Clock, RotateCcw, MessageSquare, X, FolderKanban,
  Download, Printer, Trash2, Save, Pencil, Lock, ChevronDown, Briefcase,
  UserIcon, CalendarIcon, FileSpreadsheet, PanelLeftClose, PanelLeft, Maximize2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/layout/SidebarContext";
import { NewDocumentModal } from "@/components/projects/NewDocumentModal";
import { ProposalTemplate, type ProposalEvidence, type ProposalEvidenceEntries, type ProposalEvidenceItem } from "@/components/documents/ProposalTemplate";
import { EvidencePanel } from "@/components/documents/EvidencePanel";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import { exportReqSpecExcel } from "@/lib/exportReqSpecExcel";
import { exportReqSpecPptx } from "@/lib/exportReqSpecPptx";
import type { ProposalDoc, ReqSpecDoc } from "@/lib/documentTemplates";
import { Toast } from "@/components/ui/Toast";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ColGroupDef } from "ag-grid-community";

// 2026-09-15: "업무 일정 보기" 간트를 실제 스프레드시트 UI(AG Grid)로 렌더링한다.
// 모듈 등록은 파일당 한 번만 하면 되므로 컴포넌트 바깥(모듈 스코프)에서 실행한다.
ModuleRegistry.registerModules([AllCommunityModule]);
import {
  bareStatus, stepDone, stageOf,
  PIPELINE_STEPS, PIPELINE_TAB_LABEL,
  type BareStatus, type PipelineTab,
} from "@/lib/documentPipeline";

// ── Django 응답 shape ──────────────────────────────────────────
type SpecStatusCode = "PROPOSAL_DRAFT" | "PROPOSAL_PENDING_REVIEW" | "PROPOSAL_APPROVED" | "PROPOSAL_REJECTED";

type SpecDto = {
  id: number;
  version: number;
  parent_spec: number | null;
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
  evidence_items: string | null;
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
  parent_definition: number | null;
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
  // 2026-09-16 (사용자 요청): 재배정 후에도 "AI가 원래 누굴 추천했었는지" 알 수 있게
  // — 확정 시점에 보존해둔 값이라 재배정해도 안 바뀐다.
  original_assigned_user: number | null;
  original_assigned_user_name: string | null;
  // 2026-09-16 (사용자 요청 — 재배정 잠금 예외): 담당자가 퇴사 처리됐으면 승인/진행중/완료
  // 상태여도 재배정 드롭박스를 열어준다(안 그러면 그 업무가 영영 재배정 못 하고 붕 뜸).
  assigned_user_resigned: boolean;
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
  parent_task_id: string | null; // 2026-09-17: Subtask일 때만 원본 Task의 task_id(예: "TASK-001")
  // 2026-09-22: Subtask로 쪼개진 Task 자신을 표시만 하기 위한 행 — 배정 대상이
  // 아니라 assignee_id/날짜가 항상 비어있다.
  is_task_header: boolean;
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
  parent_task_id: string | null; // 2026-09-17
  is_task_header: boolean; // 2026-09-22
  start_date: string; // yyyy-mm-dd, <input type="date"> 용 — 없으면 빈 문자열
  end_date: string;
};

type Member = { id: number; name: string; jobRoleCode: string | null };

// 업무 자체엔 "직무" 필드가 없어서, 담당자 계정의 job_role_code로 대신 집계한다.
// 2026-09-17: 원래 4개 직무만 라벨이 있고 나머지(풀스택/PM/QA/디자이너)는 전부
// "미분류"로 뭉뚱그렸는데, 실제 데이터로 확인해보니 FULLSTACK만 해도 배정 인원의
// 상당수를 차지해 "미분류"가 실질적으로 의미 없이 커지는 문제가 있었다(사용자
// 리포트로 확인) — USER_JOB_ROLE 8개 전부에 라벨을 준다. 이제 "미분류"는 정말
// job_role_code가 비어있거나(미등록) 알 수 없는 값일 때만 남는다.
const JOB_ROLE_LABEL: Record<string, string> = {
  BACKEND: "백엔드",
  FRONTEND: "프론트",
  DATA_ENGINEER: "데이터",
  DEVOPS: "데브옵스",
  QA_ENGINEER: "QA",
  UIUX_DESIGNER: "디자인",
  FULLSTACK: "풀스택",
  PROJECT_MANAGER: "PM",
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
  parent_task_id: s.parent_task_id,
  is_task_header: s.is_task_header,
  start_date: toDateInput(s.suggested_start_date),
  end_date: toDateInput(s.suggested_end_date),
});

// 담당자별로 업무 막대를 배치하는 간트 차트에 넘길 공통 아이템 — heyzzabi2의 GanttItem과
// 동일한 모양이라 draft/confirmed 둘 다 이걸로 변환해서 같은 GanttChart를 재사용한다.
type GanttItem = {
  id: string; title: string; assigneeName: string; start: string; end: string;
  epicNo: string; epicTitle: string; // 2026-09-22: 간트에서도 어느 Epic 소속인지 보이게
};

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
  const { setIsOpen: setAppSidebarOpen } = useSidebar();

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
  // 2026-09-14: "업무 배분 실행"이 순차 LLM 호출 여러 개라 1~수 분 걸리는 게
  // 정상이다("느리다" 문의 확인) — 폴링 중 현재 단계를 보여줘 체감을 낮춘다.
  const genTasksSeqRef = useRef(0);
  const [generatingStage, setGeneratingStage] = useState("");
  const [generatingStartedAt, setGeneratingStartedAt] = useState<number | null>(null);
  // 2026-09-15: 기획서 생성(analyze)도 업무 배분과 같은 job/폴링 구조로 바꿔
  // 진행 단계(회의록 분석 → 기획서 초안 생성)를 보여준다.
  const specGenSeqRef = useRef(0);
  const [specGenStartedAt, setSpecGenStartedAt] = useState<number | null>(null);
  const [specGenStage, setSpecGenStage] = useState("");
  const [confirmingTasks, setConfirmingTasks] = useState(false);
  const [reassigningTaskId, setReassigningTaskId] = useState<number | null>(null);
  const [approvingAllTasks, setApprovingAllTasks] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  // 2026-09-17: 문서를 골라 보고 있다가 새로고침(F5)하면 선택이 풀려서 목록 맨 위
  // 문서로 돌아가 버린다는 요청 — 선택 상태를 URL 쿼리(?note=)에 반영해서, 새로고침
  // 해도 같은 문서를 그대로 보여준다. 최초 렌더에서 쿼리값으로 시작해야 목록이 아직
  // 안 불러와진 순간에도 깜빡임 없이 바로 그 문서를 가리킨다.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(() => {
    const q = searchParams.get("note");
    return q ? Number(q) : null;
  });
  const [activeTab, setActiveTab] = useState<PipelineTab>("proposal");
  const [newDocModalOpen, setNewDocModalOpen] = useState(false);
  // 좌측 전체 사이드바와 별개로, 이 화면 안의 문서 목록 패널도 접을 수 있게 해달라는
  // 요청 — 문서 하나를 골라 기획서/요구사항정의서를 오래 들여다볼 때는 목록이 필요
  // 없어서 공간을 넓게 쓰고 싶은 경우가 많다. 세션 중에만 유지하면 되는 UI 상태라
  // localStorage 등에 영속시키지 않는다.
  const [listCollapsed, setListCollapsed] = useState(false);
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
      .catch(() => { });
  }, []);

  // 2026-09-15: updated_at 기준 정렬이었으나, 카드에 보이는 날짜는 meeting_date(수동
  // 입력값)라 정렬 순서와 화면에 보이는 날짜가 안 맞아 보인다는 피드백 — "등록된 순서"
  // 즉 실제 생성 시각(created_at) 기준 최신순으로 바꾼다.
  const sortedNotes = useMemo(
    () => notes.slice().sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [notes]
  );
  const selectedNote = useMemo(
    () => sortedNotes.find(n => n.id === selectedNoteId) ?? sortedNotes[0] ?? null,
    [sortedNotes, selectedNoteId]
  );
  useEffect(() => {
    if (!selectedNoteId && sortedNotes.length > 0) setSelectedNoteId(sortedNotes[0].id);
  }, [sortedNotes, selectedNoteId]);
  // URL의 ?note= 값을 선택 상태와 계속 맞춘다 — router.replace라 히스토리를 새로
  // 쌓지 않고(뒤로가기가 문서 하나하나를 안 거침), 새로고침 시 이 값을 그대로
  // 읽어 위 useState 초기값으로 복원된다.
  useEffect(() => {
    if (!selectedNoteId) return;
    const current = searchParams.get("note");
    if (current === String(selectedNoteId)) return;
    router.replace(`${pathname}?note=${selectedNoteId}`, { scroll: false });
  }, [selectedNoteId, pathname, router, searchParams]);
  // taskDrafts/taskDraftsReqDefId는 selectedNote와 무관한 전역 state라, 문서를 바꿔도
  // 저절로 안 지워진다 — A 문서에서 "업무 배분 실행"으로 draft를 만든 뒤 확정하지 않고
  // B 문서로 넘어가면, B의 배분 화면에 A의 draft가 그대로 보이고 그 상태로 "배분 확정"을
  // 누르면 B의 spec에 A의 req_def_id로 확정 요청이 나가는 사고로 이어진다(실제로 코드
  // 추적해 확인). 선택된 문서가 바뀔 때마다 무조건 리셋해 이 경로를 원천 차단한다.
  useEffect(() => {
    setTaskDrafts(null);
    setTaskDraftsReqDefId(null);
  }, [selectedNoteId]);
  // 2026-09-17: 위 리셋 직후 서버에 "아직 확정 안 된 BACKLOG 초안이 있는지" 물어봐서
  // 있으면 그대로 복원한다 — 새로고침하거나 문서를 다시 열어도 미리보기가 안 날아가게
  // 하기 위함(taskDrafts는 순수 React state라 원래는 새로고침하면 사라졌었다).
  // taskAssignment 탭으로 직접 옮겨준다 — 옮기지 않으면 stageOf가 기본으로 고르는
  // 탭(hasDraftFor 반영 전엔 reqSpec)에 머물러 있어, 탭 잠금은 풀렸어도(아래 stepper
  // 참고) 사용자가 초안이 복원된 걸 못 보고 "사라졌다"고 오인하는 문제가 실제로
  // 있었다. 실패해도 에러 토스트로 방해하지 않는다 — "업무 배분 실행"을 다시 누르면
  // 되므로 조용히 무시.
  // 2026-09-22 (사용자 리포트로 재수정): 새로고침 직후엔 useAuth(사용자 정보)와
  // notes 목록(GET /api/meetings/notes/)이 둘 다 비동기로 늦게 채워진다 — 이 effect가
  // selectedNoteId에만 의존해서, 새로고침 때 selectedNoteId는 URL에서 즉시 채워지지만
  // isPM/selectedNote는 그 뒤에 따로 값이 잡혀도(같은 selectedNoteId라 재실행 트리거가
  // 없음) 복원이 영영 실행되지 않았다(실제 재현: 업무배분 실행 후 새로고침하면 초안이
  // 사라지고 다시 눌러야 함). isPM과 selectedNote(참조가 안정적인 useMemo라 값이 실제로
  // 채워질 때만 바뀜)를 의존성에 추가해 둘 다 늦게 확정돼도 다시 시도하게 한다.
  useEffect(() => {
    if (!isPM || !selectedNote) return;
    const noteId = selectedNote.id;
    const spec = selectedNote.spec_documents[0] ?? null;
    if (!spec) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch<{ has_draft: boolean; result?: GenerateTasksResult }>(
          `/api/requirements/${spec.id}/task-draft/`
        );
        if (cancelled || selectedNoteId !== noteId) return;
        if (res.has_draft && res.result) {
          setTaskDrafts((res.result.suggestions ?? []).map(suggestionToDraft));
          setTaskDraftsReqDefId(res.result.req_def_id ?? null);
          setScheduleSummary(res.result.schedule_summary ?? null);
          setPackageSplits(res.result.package_splits ?? []);
          setPlanReview(res.result.plan_review ?? null);
          setPlanBriefing(res.result.plan_briefing ?? null);
          setActiveTab("taskAssignment");
          setToastMessage("저장된 업무 배분 초안을 불러왔습니다. 검토 후 확정해주세요.");
        }
      } catch {
        // 조용히 무시 — 위 주석 참고
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNoteId, isPM, selectedNote]);
  // 업무배분 탭을 열었을 때 이미 배분된 업무가 있으면 보여준다(재배분 직후뿐 아니라
  // 문서를 다시 열었을 때도). 2026-09-11: 예전엔 selectedNote.project로 매번 "선택된
  // 노트의 프로젝트"만 좁혀서 가져왔는데, 문서 목록 카드마다 표시하는 미니 파이프라인도
  // 이 값을 그대로 쓰다 보니 "지금 보고 있는 노트의 프로젝트 데이터"로 다른 프로젝트
  // 카드들의 진행 단계까지 잘못 계산되는 버그가 있었다(실제 재현: 노트를 바꿀 때마다
  // 다른 카드의 파이프라인 점이 같이 바뀜). req_item ID는 프로젝트를 넘나들어도 겹치지
  // 않으므로, 선택된 노트와 무관하게 전체를 한 번에 가져오면 각자 자기 reqDef.items로
  // 걸러지는 기존 필터링 로직(hasConfirmedTasksFor/tasksForReqDef)이 그대로 정확해진다.
  useEffect(() => {
    fetchTaskAssignments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);
  // reqDef/taskAssignments를 아는 채로 stageOf/stepDone을 호출하기 위한 헬퍼 —
  // 요구사항정의서 승인·업무배분 확정까지 반영해 "지금 이 문서가 실제로 어디까지
  // 왔는지" 정확히 판단한다(documentPipeline.ts 참고).
  const reqDefFor = (spec: SpecDto | null) => (spec ? reqDefs.find(r => r.spec === spec.id) ?? null : null);
  const hasConfirmedTasksFor = (reqDef: ReqDefDto | null) => {
    if (!reqDef) return false;
    const itemIds = new Set(reqDef.items.map(i => i.id));
    return taskAssignments.some(t => itemIds.has(t.req_item));
  };
  // 2026-09-17: BACKLOG 초안(미확정)이 있으면 taskAssignment 탭에 "도달"은 가능해야
  // 한다(완료는 아니지만) — stageOf에 넘겨서 새로고침 후에도 탭이 안 잠기게 한다.
  // taskDrafts는 위 복원 effect가 채워주므로, 지금 보고 있는 reqDef와 맞는지만 확인한다.
  const hasDraftFor = (reqDef: ReqDefDto | null) =>
    !!reqDef && taskDraftsReqDefId === reqDef.id && !!taskDrafts && taskDrafts.length > 0;

  // 문서를 고르면(직접 클릭이든, 등록 직후 자동이든) 항상 "그 문서가 지금 있는 단계"를
  // 첫 화면으로 보여준다 — heyzzabi2와 동일한 동작.
  const selectNote = (note: NoteDto) => {
    setSelectedNoteId(note.id);
    const spec = note.spec_documents[0] ?? null;
    const reqDef = reqDefFor(spec);
    setActiveTab(stageOf(spec, reqDef, hasConfirmedTasksFor(reqDef), hasDraftFor(reqDef)));
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

  // 2026-09-22 (사용자 요청): 기획서가 생성되면 상단의 원본 회의록은 더 볼 일이
  // 없어지고(참고자료는 우측 근거 패널로 대체) 중앙 콘텐츠를 넓게 봐야 하니, 문서
  // 목록 패널과 앱 좌측 메인 내비게이션까지 둘 다 기본으로 접어둔다. 기획서가 아직
  // 없는 문서를 열면 다시 펼쳐서 원래 기본값으로 돌아간다 — "그 문서를 열었을 때의
  // 기본값"이라 사용자가 수동으로 펼치거나 접어도 다른 문서로 옮겨가면 새로 평가된다.
  useEffect(() => {
    if (!selectedNote) return;
    const spec = selectedNote.spec_documents[0] ?? null;
    const hasSpec = !!spec;
    setListCollapsed(hasSpec);
    setAppSidebarOpen(!hasSpec);
  }, [selectedNote?.id, selectedNote?.spec_documents[0]?.status_code]);

  const replaceNote = (updated: NoteDto) => {
    setNotes(prev => prev.map(n => (n.id === updated.id ? updated : n)));
  };
  const refetchNote = async (noteId: number) => {
    const note = await apiFetch<NoteDto>(`/api/meetings/notes/${noteId}/`);
    replaceNote(note);
  };

  const handleGenerateSpec = async (note: NoteDto) => {
    const seq = ++specGenSeqRef.current;
    setBusy(`${note.id}-generate`);
    setSpecGenStartedAt(Date.now());
    setSpecGenStage("회의록 구조화 중…");
    const stop = () => {
      setBusy(null);
      setSpecGenStartedAt(null);
      setSpecGenStage("");
    };
    try {
      const started = await apiFetch<{ status: string; job_id?: string }>(
        `/api/meetings/notes/${note.id}/analyze/`,
        { method: "POST" }
      );
      if (started.status !== "started" || !started.job_id) {
        setErrorToast("기획서 생성에 실패했습니다.");
        stop();
        return;
      }

      const poll = async (): Promise<void> => {
        if (specGenSeqRef.current !== seq) return;
        let job: { status: string; stage?: string; message?: string; result?: { created_spec?: SpecDto } };
        try {
          job = await apiFetch<{ status: string; stage?: string; message?: string; result?: { created_spec?: SpecDto } }>(
            `/api/meetings/notes/analyze-jobs/${started.job_id}/`
          );
        } catch (err: any) {
          if (specGenSeqRef.current !== seq) return;
          setErrorToast(err.message || "기획서 생성 진행 상태를 확인하지 못했습니다.");
          stop();
          return;
        }
        if (specGenSeqRef.current !== seq) return;

        if (job.status === "PENDING" || job.status === "RUNNING") {
          if (job.stage) setSpecGenStage(job.stage);
          setTimeout(poll, 1500);
          return;
        }
        if (job.status === "ERROR") {
          setErrorToast(job.message || "기획서 생성에 실패했습니다.");
          stop();
          return;
        }

        // SUCCESS
        await refetchNote(note.id);
        setToastMessage("기획서 생성이 완료되었습니다");
        stop();
      };
      await poll();
    } catch (err: any) {
      if (specGenSeqRef.current !== seq) return;
      setErrorToast(err.message || "기획서 생성에 실패했습니다.");
      stop();
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
  // 2026-09-15: 요구사항정의서 생성/재생성도 업무 배분·기획서 생성과 같은
  // 백그라운드 job + 폴링 구조로 바꿨다 — LLM 호출(1회 + baseline 누락 시
  // 재시도)이라 동기로 두면 오래 걸릴 수 있다. "생성"(handleCreateReqDef)과
  // "재생성"(handleExtractItems) 모두 같은 종류의 작업이라 진행 상태 state를
  // 공유한다(동시에 둘 다 눌릴 일은 없음 — busy가 하나뿐이라 버튼 자체가 막힘).
  const reqExtractSeqRef = useRef(0);
  const [reqExtractStage, setReqExtractStage] = useState("");
  const [reqExtractStartedAt, setReqExtractStartedAt] = useState<number | null>(null);

  const handleCreateReqDef = async (note: NoteDto, spec: SpecDto) => {
    const seq = ++reqExtractSeqRef.current;
    setBusy(`${spec.id}-create-reqdef`);
    setReqExtractStartedAt(Date.now());
    setReqExtractStage("요구사항 초안 생성 중…");
    const stop = () => {
      setBusy(null);
      setReqExtractStartedAt(null);
      setReqExtractStage("");
    };
    try {
      const started = await apiFetch<{ status: string; job_id?: string }>("/api/requirements/", {
        method: "POST",
        body: JSON.stringify({
          spec: spec.id,
          project: note.project,
          title: `${spec.title} 요구사항정의서`,
          version: "v1.0",
        }),
      });
      if (started.status !== "started" || !started.job_id) {
        setErrorToast("요구사항 정의서 생성에 실패했습니다.");
        stop();
        return;
      }

      const poll = async (): Promise<void> => {
        if (reqExtractSeqRef.current !== seq) return;
        let job: { status: string; stage?: string; message?: string };
        try {
          job = await apiFetch<{ status: string; stage?: string; message?: string }>(
            `/api/requirements/extraction-jobs/${started.job_id}/`
          );
        } catch (err: any) {
          if (reqExtractSeqRef.current !== seq) return;
          setErrorToast(err.message || "요구사항 정의서 생성 진행 상태를 확인하지 못했습니다.");
          stop();
          return;
        }
        if (reqExtractSeqRef.current !== seq) return;

        if (job.status === "PENDING" || job.status === "RUNNING") {
          if (job.stage) setReqExtractStage(job.stage);
          setTimeout(poll, 1500);
          return;
        }
        if (job.status === "ERROR") {
          setErrorToast(job.message || "요구사항 정의서 생성에 실패했습니다.");
          stop();
          return;
        }

        // SUCCESS
        const allReqDefs = await apiFetch<ReqDefDto[]>("/api/requirements/");
        setReqDefs(allReqDefs);
        setToastMessage("요구사항 정의서가 생성되었습니다");
        stop();
      };
      await poll();
    } catch (err: any) {
      if (reqExtractSeqRef.current !== seq) return;
      setErrorToast(err.message || "요구사항 정의서 생성에 실패했습니다.");
      stop();
    }
  };

  const handleExtractItems = async (specId: number, reqDefId: number) => {
    const seq = ++reqExtractSeqRef.current;
    setBusy(`reqdef-${reqDefId}-extract`);
    setReqExtractStartedAt(Date.now());
    setReqExtractStage("요구사항 초안 생성 중…");
    const stop = () => {
      setBusy(null);
      setReqExtractStartedAt(null);
      setReqExtractStage("");
    };
    try {
      const started = await apiFetch<{ status: string; job_id?: string }>(
        `/api/requirements/${specId}/extract/`,
        { method: "POST" }
      );
      if (started.status !== "started" || !started.job_id) {
        setErrorToast("요구사항정의서 재생성에 실패했습니다.");
        stop();
        return;
      }

      const poll = async (): Promise<void> => {
        if (reqExtractSeqRef.current !== seq) return;
        let job: { status: string; stage?: string; result?: ReqDefDto; message?: string };
        try {
          job = await apiFetch<{ status: string; stage?: string; result?: ReqDefDto; message?: string }>(
            `/api/requirements/extraction-jobs/${started.job_id}/`
          );
        } catch (err: any) {
          if (reqExtractSeqRef.current !== seq) return;
          setErrorToast(err.message || "요구사항정의서 재생성 진행 상태를 확인하지 못했습니다.");
          stop();
          return;
        }
        if (reqExtractSeqRef.current !== seq) return;

        if (job.status === "PENDING" || job.status === "RUNNING") {
          if (job.stage) setReqExtractStage(job.stage);
          setTimeout(poll, 1500);
          return;
        }
        if (job.status === "ERROR") {
          setErrorToast(job.message || "요구사항정의서 재생성에 실패했습니다.");
          stop();
          return;
        }

        // SUCCESS
        const updatedReqDef = job.result;
        if (updatedReqDef) {
          setReqDefs(prev => prev.map(r => r.id === reqDefId ? updatedReqDef : r));
          const itemCount = updatedReqDef.items?.length || 0;
          setToastMessage(`요구사항정의서가 재생성되었습니다 (${itemCount}건)`);
        }
        stop();
      };
      await poll();
    } catch (err: any) {
      if (reqExtractSeqRef.current !== seq) return;
      setErrorToast(err.message || "요구사항정의서 재생성에 실패했습니다.");
      stop();
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

  // project 쿼리 파라미터 없이 호출하면 백엔드가 전체 프로젝트의 배정 업무를 돌려준다
  // (tasks/views.py TaskAssignmentViewSet.get_queryset 참고) — 문서 목록의 카드마다
  // 자기 reqDef.items의 req_item ID로 걸러 쓰므로(hasConfirmedTasksFor/tasksForReqDef),
  // 어느 노트가 선택돼 있든 항상 전체를 들고 있으면 각 카드가 정확히 자기 프로젝트
  // 기준으로 계산된다. 여러 곳(초기 로드/배분 확정 후/재배정 후)에서 겹쳐 호출될 수
  // 있어 마지막으로 시작한 요청의 결과만 반영하도록 순번을 매겨 낡은 응답은 버린다.
  const taskFetchSeqRef = useRef(0);
  const fetchTaskAssignments = async () => {
    const seq = ++taskFetchSeqRef.current;
    try {
      const list = await apiFetch<TaskAssignmentDto[]>(`/api/tasks/assignments/`);
      if (taskFetchSeqRef.current !== seq) return; // 낡은 응답 — 그사이 더 최근 요청이 나감
      setTaskAssignments(list);
    } catch (err: any) {
      if (taskFetchSeqRef.current !== seq) return;
      setErrorToast(err.message || "업무 목록을 불러오지 못했습니다.");
    }
  };

  type GenerateTasksResult = {
    status: string; message?: string; suggestions?: TaskSuggestionDto[]; req_def_id?: number;
    schedule_summary?: ScheduleSummaryDto; package_splits?: PackageSplitDto[];
    plan_review?: PlanReviewDto; plan_briefing?: PlanBriefingDto;
  };
  type GenerateTasksJobStatus = {
    status: "PENDING" | "RUNNING" | "SUCCESS" | "ERROR"; stage?: string;
    result?: GenerateTasksResult; message?: string;
  };

  // heyzzabi2의 "업무 배분 실행" — 요구사항정의서 승인 후 PM이 눌러서 실제 AI
  // 파이프라인(업무생성→담당자매핑→담당자추천)을 돌린다. 이 단계는 미리보기(제안)만
  // 만들고 DB에는 아무것도 저장하지 않는다 — PM이 담당자/일정을 검토·수정한 뒤
  // "배분 확정"을 눌러야 handleConfirmTasks가 실제로 저장한다(2단계 확정 플로우).
  //
  // 2026-09-14: 순차 LLM 호출 여러 개라 1~수 분 걸리는 게 정상이라("느리다" 문의
  // 확인 결과), 백엔드가 즉시 job_id만 돌려주고 실제 파이프라인은 백그라운드로
  // 돈다. 여기서는 job_id로 폴링하며 현재 단계를 보여주다가, 완료되면 기존과
  // 동일하게 결과를 반영한다. genTasksSeqRef는 폴링 도중 사용자가 다시 실행
  // 버튼을 누르거나 다른 문서로 넘어갔을 때 오래된 폴링 루프가 새 상태를
  // 덮어쓰지 않도록 막는다(다른 곳의 taskFetchSeqRef와 같은 패턴).
  const handleGenerateTasks = async (spec: SpecDto, reqDefId: number) => {
    const seq = ++genTasksSeqRef.current;
    setGeneratingTasks(true);
    setGeneratingStage("작업을 준비하는 중…");
    setGeneratingStartedAt(Date.now());
    setBusy(`reqdef-${reqDefId}-tasks`);
    const stop = () => {
      setGeneratingTasks(false);
      setGeneratingStartedAt(null);
      setBusy(null);
    };
    try {
      const started = await apiFetch<{ status: string; job_id?: string }>(
        `/api/requirements/${spec.id}/generate-tasks/`,
        { method: "POST" }
      );
      if (started.status !== "started" || !started.job_id) {
        setErrorToast("업무 배분 제안 생성에 실패했습니다.");
        stop();
        return;
      }

      const poll = async (): Promise<void> => {
        if (genTasksSeqRef.current !== seq) return;
        let job: GenerateTasksJobStatus;
        try {
          job = await apiFetch<GenerateTasksJobStatus>(`/api/requirements/generate-tasks-jobs/${started.job_id}/`);
        } catch (err: any) {
          if (genTasksSeqRef.current !== seq) return;
          setErrorToast(err.message || "업무 배분 진행 상태를 확인하지 못했습니다.");
          stop();
          return;
        }
        if (genTasksSeqRef.current !== seq) return;

        if (job.status === "PENDING" || job.status === "RUNNING") {
          if (job.stage) setGeneratingStage(job.stage);
          setTimeout(poll, 1500);
          return;
        }
        if (job.status === "ERROR") {
          setErrorToast(job.message || "업무 배분 제안 생성에 실패했습니다.");
          stop();
          return;
        }

        // SUCCESS
        const result = job.result;
        if (!result || result.status !== "success") {
          setErrorToast(result?.message || "업무 배분 제안 생성에 실패했습니다.");
          stop();
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
        stop();
      };
      await poll();
    } catch (err: any) {
      if (genTasksSeqRef.current !== seq) return;
      setErrorToast(err.message || "업무 배분 제안 생성에 실패했습니다.");
      stop();
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
                parent_task_id: d.parent_task_id, // 2026-09-17
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
      await fetchTaskAssignments();
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
      await fetchTaskAssignments();
    } catch (err: any) {
      setErrorToast(err.message || "담당자 변경에 실패했습니다.");
    } finally {
      setReassigningTaskId(null);
    }
  };

  // 2026-09-18 (사용자 요청): 배분 승인/반려를 담당자 본인 전용으로 좁혔던 정책(9/16)을
  // 되돌려 PM도 다시 승인할 수 있게 했다(백엔드 TaskStatusUpdateView 권한 체크 참고) —
  // 이 문서생성 화면에서 PENDING_APPROVAL 건 전체를 한 번에 TASK_APPROVED로 승인한다.
  const handleApproveAllTasks = async (taskIds: number[]) => {
    if (taskIds.length === 0) return;
    setApprovingAllTasks(true);
    try {
      await Promise.all(taskIds.map(id => apiFetch(`/api/tasks/assignments/${id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: "TASK_APPROVED" }),
      })));
      setToastMessage(`업무 배분이 확정되었습니다 — ${taskIds.length}건`);
      await fetchTaskAssignments();
    } catch (err: any) {
      setErrorToast(err.message || "업무 배분 확정에 실패했습니다.");
    } finally {
      setApprovingAllTasks(false);
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
          // 2026-09-17: 미확정 BACKLOG 초안만 있어도 taskAssignment 탭은 잠기면 안 된다
          // (locked 판정이 currentStageIndex 기준이라, stageOf가 hasDraft를 몰라 "reqSpec"에
          // 머물면 탭 자체가 잠겨 복원된 초안을 볼 방법이 없어짐 — 실제 재현된 버그).
          const currentStage = stageOf(activeSpec, activeReqDef, hasConfirmedTasks, hasDraftFor(activeReqDef));
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

      <div className={cn(
        "grid grid-cols-1 gap-6 items-start transition-[grid-template-columns] duration-200",
        listCollapsed ? "lg:grid-cols-[56px_minmax(0,1fr)]" : "lg:grid-cols-[360px_minmax(0,1fr)]"
      )}>
        {/* Document list — PDF 다운로드(window.print())는 #print-area 외 나머지를
            visibility:hidden으로만 숨기는데, 이 목록은 스크롤 없이 카드 전부(100개+)를
            그대로 렌더링해서 visibility:hidden이어도 레이아웃 높이는 그대로 차지한다.
            그 결과 body 전체 높이가 목록 길이만큼 부풀어서 실제 기획서 뒤에 빈 페이지가
            수십 장 따라붙는 버그가 있었다(실제 보고됨) — print-area의 조상이 아니라
            형제 요소라 display:none(print:hidden)으로 완전히 레이아웃에서 빼도 안전하다. */}
        <div className={cn(
          "glass rounded-2xl border border-border print:hidden transition-all",
          listCollapsed
            ? "p-2 flex flex-col items-center"
            : "p-4 flex flex-col gap-3 sticky top-6 max-h-[calc(100vh-3rem)]"
        )}>
          {listCollapsed ? (
            <button
              onClick={() => setListCollapsed(false)}
              title="문서 목록 펼치기"
              aria-label="문서 목록 펼치기"
              className="p-2.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2 shrink-0">
                <span className="text-sm font-bold text-muted-foreground pl-1">문서 목록</span>
                <button
                  onClick={() => setListCollapsed(true)}
                  title="문서 목록 접기"
                  aria-label="문서 목록 접기"
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors shrink-0"
                >
                  <PanelLeftClose className="w-4 h-4" />
                </button>
              </div>
              {!isPM && (
                <button
                  onClick={() => setNewDocModalOpen(true)}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 transition-colors shrink-0"
                >
                  <Plus className="w-4 h-4" /> 새 회의록 / 문서
                </button>
              )}

              <div className="space-y-2 overflow-y-auto min-h-0 flex-1 pr-1 -mr-1">
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
                            {/* 2026-09-15: meeting_date(회의 날짜, 수동 입력값)를 보여주면 목록
                            정렬 기준(등록일=created_at)과 화면에 보이는 날짜가 달라서 "최신순인데
                            맨 위가 옛날 날짜"로 보이는 혼란이 있었다 — 정렬 기준과 같은 날짜를 표시. */}
                            <span>{new Date(note.created_at).toLocaleDateString("ko-KR")}</span>
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
            </>
          )}
        </div>

        {/* Detail panel. min-w-0: 이 div는 2단 그리드(360px_minmax(0,1fr))의 직접
            그리드 아이템이다. 트랙 자체를 minmax(0,1fr)로 잡아도 그리드 "아이템"의
            기본 min-width는 auto(=콘텐츠의 최소 폭)라서, 안쪽 깊숙이 있는 넓은 콘텐츠
            (Gantt 등)가 있으면 이 아이템이, 결국 트랙 전체가 같이 넓어져 버린다(팀원
            리포트: WBS 펼쳐도 하단 스크롤이 안 생기고 카드 자체가 넓어짐) — min-w-0으로
            그 기본값을 꺼야 안쪽의 overflow-x-auto가 실제로 스크롤로 동작한다. */}
        <div className="glass rounded-2xl border border-border p-6 min-h-[500px] min-w-0">
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
              projectName={project?.name}
              specGenStartedAt={specGenStartedAt}
              specGenStage={specGenStage}
              onGenerateSpec={() => handleGenerateSpec(selectedNote)}
              onSaveNoteContent={(content) => handleSaveNoteContent(selectedNote, content)}
              onSaveSpec={(spec, doc) => handleSaveSpec(selectedNote, spec, doc)}
              onSavePeriod={(spec, period) => handleSavePeriod(selectedNote, spec, period)}
              onSubmitReview={(spec) => handleSubmitReview(selectedNote, spec)}
              onApprove={(spec) => handleApprove(selectedNote, spec)}
              onReject={(spec) => setRejectTarget({ kind: "spec", specId: spec.id })}
              onCreateReqDef={(spec) => handleCreateReqDef(selectedNote, spec)}
              onExtractItems={handleExtractItems}
              reqExtractStage={reqExtractStage}
              reqExtractStartedAt={reqExtractStartedAt}
              onAddItem={handleAddItem}
              onUpdateItem={handleUpdateItem}
              onDeleteItem={handleDeleteItem}
              onReqDefStatusChange={handleReqDefStatusChange}
              onGenerateTasks={(spec, reqDefId) => handleGenerateTasks(spec, reqDefId)}
              onRejectReqDef={(spec, reqDefId) => setRejectTarget({ kind: "reqdef", specId: spec.id, reqDefId })}
              taskAssignments={taskAssignments}
              taskDrafts={taskDrafts}
              taskDraftsReqDefId={taskDraftsReqDefId}
              setTaskDrafts={setTaskDrafts}
              scheduleSummary={scheduleSummary}
              packageSplits={packageSplits}
              planReview={planReview}
              planBriefing={planBriefing}
              generatingTasks={generatingTasks}
              generatingStage={generatingStage}
              generatingStartedAt={generatingStartedAt}
              confirmingTasks={confirmingTasks}
              onConfirmTasks={(spec) => handleConfirmTasks(selectedNote, spec)}
              onCancelTaskDrafts={() => { setTaskDrafts(null); setTaskDraftsReqDefId(null); setScheduleSummary(null); setPackageSplits([]); setPlanReview(null); setPlanBriefing(null); }}
              members={members}
              reassigningTaskId={reassigningTaskId}
              onReassignTask={(taskId, assigneeId) => handleReassignTask(selectedNote, taskId, assigneeId)}
              approvingAllTasks={approvingAllTasks}
              onApproveAllTasks={handleApproveAllTasks}
            />
          )}
        </div>
      </div>

      {newDocModalOpen && (
        <NewDocumentModal
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

// 2026-09-15: "업무 배분 실행" 진행 단계 라벨(services.py _stage 호출 문자열)을
// 5개의 고정 파이프라인 단계에 매핑한다 — 실제 문구는 자유 텍스트(예: "총 3명
// 배정 중 — 홍길동 외 2명")라 정확한 %는 알 수 없지만, 어느 단계인지는 구분 가능하다.
const TASK_GEN_STAGES: { label: string; match: (s: string) => boolean }[] = [
  { label: "업무 생성", match: (s) => s.includes("업무 생성") },
  { label: "규모 판단", match: (s) => s.includes("프로젝트 규모") },
  { label: "패키지 분할", match: (s) => s.includes("패키지 분할") },
  { label: "담당자 분석", match: (s) => s.includes("담당자 정보 분석") },
  {
    label: "담당자 배정",
    match: (s) =>
      s.includes("담당자 배정") || s.startsWith("총 ") || s.includes("사유 작성") ||
      s.includes("배정 가능한 담당자가 없어"),
  },
  // 2026-09-15: "계획 요약 작성 중…" 단계가 이 목록에 없어서, 해당 단계에 들어가면
  // currentStageIndex가 매칭되는 단계를 못 찾고 0(업무 생성)으로 되돌아가 보이던
  // 문제 수정 — 마지막 단계로 추가한다.
  { label: "계획 요약", match: (s) => s.includes("계획 요약") },
];

// 단계 라벨을 대략의 진행률(%)로도 매핑한다 — 정확한 값은 아니지만(파이프라인
// 각 단계가 실제로 몇 %인지는 알 수 없음), 아래 "남은 시간"을 "지금까지 걸린
// 시간 ÷ 진행률"로 역산하는 데 쓴다. "(3/8건)"처럼 실제 분모/분자가 찍히는
// 단계는 그 비율을 그대로 반영한다.
function taskGenStageProgressPercent(stage: string, _elapsedSec: number): number {
  // 2026-09-15: "담당자 배정 추천 중…"(이 단계 진입 시 맨 처음 뜨는 문구)이
  // 아래 어느 조건에도 안 걸려서 항상 5%로 떨어지던 문제 수정 — 이 단계는
  // 실제로 전체 파이프라인의 절반을 넘긴 지점(50%대)인데 5%로 되돌아가
  // 보이면서 "남은 시간"도 같이 크게 튀었다. 또한 마지막 단계인 "계획 요약
  // 작성 중…"도 매칭되는 게 없어 5%로 떨어졌던 것도 같이 고친다.
  if (stage.includes("계획 요약")) return 97;
  const ratioMatch = stage.match(/\((\d+)\/(\d+)\D*\)/);
  if (ratioMatch) {
    const done = Number(ratioMatch[1]);
    const total = Number(ratioMatch[2]) || 1;
    return Math.min(96, 60 + Math.round((done / total) * 35));
  }
  if (stage.includes("배정 가능한 담당자가 없어")) return 70;
  if (stage.startsWith("총 ") && stage.includes("배정")) return 60;
  if (stage.includes("사유 작성")) return 62;
  if (stage.includes("담당자 배정")) return 55;
  if (stage.includes("담당자 정보 분석")) return 50;
  if (stage.includes("업무 패키지 분할")) return 38;
  if (stage.includes("프로젝트 규모 판단")) return 25;
  if (stage.includes("업무 생성")) return 10;
  return 5;
}

// 2026-09-15: "기획서 생성"(회의록 분석 → 기획서 초안 생성)도 업무 배분과 같은
// 백그라운드 job + 폴링 구조로 바꿨다. 처음엔 "회의록 분석 중…" / "기획서 초안
// 생성 중…" 2단계로만 뭉뚱그렸는데, 업무 배분만큼 세세하게 보여달라는 요청으로
// 노드 내부 단계(ai/meeting_analysis/node.py, ai/plan_draft/agent.py)까지
// on_stage로 보고하도록 넓혔다 — 실제 LLM 호출은 여전히 2번뿐이지만(노드①
// 구조화, 노드② 초안작성) 그 사이 코드 단계(근거검증/정합성검사/목록조립/병합)도
// 각자 라벨을 보고해 진행 중임을 더 자주 보여준다.
const SPEC_GEN_STAGES: { label: string; match: (s: string) => boolean }[] = [
  { label: "구조화", match: (s) => s.includes("구조화") },
  { label: "근거 검증", match: (s) => s.includes("근거자료 검증") },
  { label: "정합성 검사", match: (s) => s.includes("정합성 검사") },
  { label: "초안 작성", match: (s) => s.includes("초안 작성") },
  { label: "섹션 조립", match: (s) => s.includes("목록형 섹션 조립") },
  { label: "병합", match: (s) => s.includes("섹션 병합") },
];

// 2026-09-15: 단계당 고정 %였던 이전 버전은 그 단계 안에서 시간이 아무리 지나도
// %가 안 올라가서 "1분 넘게 지났는데 10%"처럼 보이고, 그 %로 역산하는 "남은
// 시간"도 같이 터무니없이 커지는 문제가 있었다(사용자 보고, 실측: 경과 1:28인데
// 남은 시간 13:12로 표시됨) — 느린 두 단계(구조화 실측 ~100초, 초안작성 추정
// ~25초)는 경과 시간에 비례해 그 안에서도 %가 계속 올라가게 하고, 나머지
// 코드뿐인 빠른 단계는 그냥 고정 % 하나씩만 준다(어차피 순식간에 지나간다).
const SPEC_GEN_STAGE1_SEC = 100; // 구조화(LLM)
const SPEC_GEN_STAGE2_SEC = 25; // 초안 작성(LLM)

function specGenStageProgressPercent(stage: string, elapsedSec: number): number {
  if (stage.includes("구조화")) {
    return Math.min(68, 5 + Math.round((elapsedSec / SPEC_GEN_STAGE1_SEC) * 63));
  }
  if (stage.includes("근거자료 검증")) return 72;
  if (stage.includes("정합성 검사")) return 76;
  if (stage.includes("초안 작성")) {
    const t = Math.max(0, elapsedSec - SPEC_GEN_STAGE1_SEC);
    return Math.min(90, 78 + Math.round((t / SPEC_GEN_STAGE2_SEC) * 12));
  }
  if (stage.includes("목록형 섹션 조립")) return 92;
  if (stage.includes("섹션 병합")) return 95;
  return 5;
}

function currentStageIndex(stages: { label: string; match: (s: string) => boolean }[], stage: string): number {
  for (let i = stages.length - 1; i >= 0; i--) {
    if (stages[i].match(stage)) return i;
  }
  return 0;
}

function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function useElapsedSeconds(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt == null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return startedAt != null ? Math.max(0, (now - startedAt) / 1000) : 0;
}

function StageTracker({ stages, current }: { stages: string[]; current: number }) {
  return (
    <div className="flex items-start gap-1.5">
      {stages.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <Fragment key={label}>
            {i > 0 && (
              <div
                className={cn(
                  "h-0.5 flex-1 mt-2.5 rounded-full transition-colors duration-500",
                  i <= current ? "bg-cyan-400" : "bg-black/10 dark:bg-white/10"
                )}
              />
            )}
            <div className="flex flex-col items-center gap-1 shrink-0">
              <div
                className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-colors duration-500",
                  done || active
                    ? "bg-cyan-500 text-white"
                    : "bg-black/10 dark:bg-white/10 text-muted-foreground/50"
                )}
              >
                {done ? (
                  <svg viewBox="0 0 24 24" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                ) : active ? (
                  <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-current" />
                )}
              </div>
              <span className={cn("text-[9px] whitespace-nowrap", active ? "text-foreground font-semibold" : "text-muted-foreground/50")}>
                {label}
              </span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

// 2026-09-22 (사용자 요청): "남은 시간"은 순차 LLM 호출 여러 개의 총 소요시간을
// 정확히 알 방법이 없어 진행률로 역산한 추정치일 뿐이라 오차가 커서(사용자 실측
// 사례: 경과 1:28인데 남은 시간 13:12로 표시) 신뢰도가 낮다는 지적 — 아예 없애고
// 경과 시간과 진행률만 보여준다.
function ProgressTimeline({
  stages, stage, pctFn, startedAt,
}: {
  stages: { label: string; match: (s: string) => boolean }[];
  stage: string;
  pctFn: (stage: string, elapsedSec: number) => number;
  startedAt: number | null;
}) {
  const current = currentStageIndex(stages, stage);
  const elapsedSec = useElapsedSeconds(startedAt);
  const pct = pctFn(stage, elapsedSec);

  return (
    <div className="flex flex-col gap-1.5 w-80 shrink-0">
      <StageTracker stages={stages.map((s) => s.label)} current={current} />
      <div className="flex items-center gap-1.5 text-[10px] font-mono tabular-nums text-muted-foreground/70">
        <span className="font-bold text-cyan-500">{pct}%</span>
        <span>·</span>
        <span>경과 {formatDuration(elapsedSec)}</span>
      </div>
    </div>
  );
}

function TaskGenProgressBar({ stage, startedAt }: { stage: string; startedAt: number | null }) {
  return <ProgressTimeline stages={TASK_GEN_STAGES} stage={stage} pctFn={taskGenStageProgressPercent} startedAt={startedAt} />;
}

function SpecGenProgressBar({ stage, startedAt }: { stage: string; startedAt: number | null }) {
  return <ProgressTimeline stages={SPEC_GEN_STAGES} stage={stage} pctFn={specGenStageProgressPercent} startedAt={startedAt} />;
}

// 2026-09-15: 요구사항정의서 생성/재생성(ai/requirement_draft/agent.py)도 업무
// 배분·기획서 생성과 같은 세세한 진행 표시를 추가한다 — LLM 호출은 1회가
// 기본이고, baseline NFR 카테고리가 누락되면 최대 MAX_RETRIES회까지 추가로
// 재시도한다(횟수가 매번 다를 수 있어 고정 단계 수로 못 박지 않는다).
const REQ_EXTRACT_STAGES: { label: string; match: (s: string) => boolean }[] = [
  { label: "초안 생성", match: (s) => s.includes("초안 생성") },
  { label: "누락 보완", match: (s) => s.includes("누락 카테고리 보완") },
  { label: "최종 검증", match: (s) => s.includes("최종 검증") },
  { label: "저장", match: (s) => s.includes("저장") },
];

const REQ_EXTRACT_STAGE1_SEC = 40; // "초안 생성"(LLM) 추정 소요시간

function reqExtractStageProgressPercent(stage: string, elapsedSec: number): number {
  const ratioMatch = stage.match(/\((\d+)\/(\d+)\)/);
  if (ratioMatch) {
    const done = Number(ratioMatch[1]);
    const total = Number(ratioMatch[2]) || 1;
    return Math.min(90, 70 + Math.round((done / total) * 20));
  }
  if (stage.includes("최종 검증")) return 92;
  if (stage.includes("저장")) return 96;
  if (stage.includes("초안 생성")) {
    return Math.min(65, 5 + Math.round((elapsedSec / REQ_EXTRACT_STAGE1_SEC) * 60));
  }
  return 5;
}

function ReqExtractProgressBar({ stage, startedAt }: { stage: string; startedAt: number | null }) {
  return <ProgressTimeline stages={REQ_EXTRACT_STAGES} stage={stage} pctFn={reqExtractStageProgressPercent} startedAt={startedAt} />;
}

function NoteDetail({
  note, spec, reqDef, activeTab, isPM, currentUserId, busy, projectName,
  onGenerateSpec, specGenStartedAt, specGenStage, onSaveNoteContent, onSaveSpec, onSavePeriod, onSubmitReview, onApprove, onReject,
  onCreateReqDef, onExtractItems, reqExtractStage, reqExtractStartedAt, onAddItem, onUpdateItem, onDeleteItem, onReqDefStatusChange,
  onGenerateTasks, taskAssignments, onRejectReqDef,
  taskDrafts, taskDraftsReqDefId, setTaskDrafts, scheduleSummary, packageSplits, planReview, planBriefing, generatingTasks, generatingStage, generatingStartedAt, confirmingTasks, onConfirmTasks, onCancelTaskDrafts,
  members, reassigningTaskId, onReassignTask, approvingAllTasks, onApproveAllTasks,
}: {
  note: NoteDto; spec: SpecDto | null; reqDef: ReqDefDto | null; activeTab: PipelineTab; isPM: boolean; currentUserId: string | undefined; busy: string | null; projectName: string | undefined;
  onGenerateSpec: () => void;
  specGenStartedAt: number | null;
  specGenStage: string;
  onSaveNoteContent: (content: string) => void;
  onSaveSpec: (spec: SpecDto, doc: ProposalDoc) => void;
  onSavePeriod: (spec: SpecDto, period: { start: string; end: string }) => void;
  onSubmitReview: (spec: SpecDto) => void;
  onApprove: (spec: SpecDto) => void;
  onReject: (spec: SpecDto) => void;
  onCreateReqDef: (spec: SpecDto) => void;
  onExtractItems: (specId: number, reqDefId: number) => void;
  reqExtractStage: string;
  reqExtractStartedAt: number | null;
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string; order: number; priority_code: string | null }) => void;
  onUpdateItem: (reqDefId: number, itemId: number, patch: { req_name: string; description: string; priority_code?: string | null }) => void;
  onDeleteItem: (reqDefId: number, itemId: number) => void;
  onReqDefStatusChange: (spec: SpecDto, reqDefId: number, statusCode: "PENDING_REVIEW" | "APPROVED") => void;
  onGenerateTasks: (spec: SpecDto, reqDefId: number) => void;
  onRejectReqDef: (spec: SpecDto, reqDefId: number) => void;
  taskAssignments: TaskAssignmentDto[];
  taskDrafts: TaskDraft[] | null;
  taskDraftsReqDefId: number | null;
  setTaskDrafts: Dispatch<SetStateAction<TaskDraft[] | null>>;
  scheduleSummary: ScheduleSummaryDto | null; // 2026-09-10 (Phase 0)
  packageSplits: PackageSplitDto[]; // 2026-09-11 (Phase 3)
  planReview: PlanReviewDto | null; // 2026-09-11 (Phase 4)
  planBriefing: PlanBriefingDto | null; // 2026-09-11 (Phase 4)
  generatingTasks: boolean;
  generatingStage: string;
  generatingStartedAt: number | null;
  confirmingTasks: boolean;
  onConfirmTasks: (spec: SpecDto) => void;
  onCancelTaskDrafts: () => void;
  members: Member[];
  reassigningTaskId: number | null;
  onReassignTask: (taskId: number, assigneeId: number) => void;
  approvingAllTasks: boolean;
  onApproveAllTasks: (taskIds: number[]) => void;
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
  const [evidenceTarget, setEvidenceTarget] = useState<{ noteId: number; sectionKey: keyof ProposalEvidence; quotes: string[]; items?: ProposalEvidenceItem[] } | null>(null);
  // 2026-09-22 (사용자 요청): 기획서 생성 직후 자동으로 열리는 기본 상태에서 패널이
  // 너무 넓어 보인다는 지적 — EvidencePanel이 허용하는 최소 폭(360, resizeFromPointer
  // 참고)으로 기본값을 낮춘다. 사용자가 드래그로 늘리면 그 값은 그대로 유지된다.
  const [evidencePanelWidth, setEvidencePanelWidth] = useState(360);
  // 2026-09-22 (사용자 요청): 기획서가 생성되고 나면(스테이터스 무관 — DRAFT부터
  // 즉시) 상단 원본 회의록 대신 우측 근거 패널을 기본으로 열어둔다 — 특정 섹션
  // 근거를 고른 게 아니므로 하이라이트 없이 원문 전체만 보여준다(evidenceTarget과
  // 분리해서, 왼쪽 카드에 "이 섹션이 활성" 표시가 잘못 붙지 않게 한다).
  const [autoEvidenceOpen, setAutoEvidenceOpen] = useState(false);
  useEffect(() => { setAutoEvidenceOpen(!!spec); }, [note.id, spec?.id]);
  const targetedEvidenceOpen = evidenceTarget?.noteId === note.id;
  const evidencePanelOpen = targetedEvidenceOpen || autoEvidenceOpen;
  const showEvidence = (sectionKey: keyof ProposalEvidence, quotes: string[], items?: ProposalEvidenceItem[]) => {
    setEvidenceTarget({ noteId: note.id, sectionKey, quotes, items });
  };

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
    <div
      // 2026-09-22 (사용자 재확인): 근거 패널/우측 여백은 기획서 탭에서만 — 요구사항정의서·
      // 업무배분 탭은 이 컨테이너를 그대로 공유해서 쓰기 때문에(탭 전환 시 상태 유지를
      // 위해 전부 mount해두고 CSS로만 감춤), activeTab을 안 걸면 다른 탭을 볼 때도 우측이
      // 패널 너비만큼 밀려서 잘려 보이는 문제가 있었다.
      className={cn("space-y-5 transition-[padding] duration-300", evidencePanelOpen && activeTab === "proposal" && "xl:pr-[var(--evidence-panel-width)]")}
      style={{ "--evidence-panel-width": `${evidencePanelWidth}px` } as React.CSSProperties}
    >
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
          {/* 2026-09-22 (사용자 요청): 여러 프로젝트를 오갈 때 지금 보고 있는 문서가
              어느 프로젝트 소속인지 헤더에서 바로 보여야 함 — 이 페이지는 항상 프로젝트
              하나로 스코프되어 있어(fetchAll 참고) note.project와 project.id가 같다. */}
          {projectName && (
            <p className="text-xs text-muted-foreground mt-0.5">
              프로젝트 {projectName}
            </p>
          )}
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
        {/* 2026-09-22 (사용자 요청): 기획서가 생성되면(rawLocked=!!spec) 원본은 더 이상
          이 자리에서 볼 일이 없다 — 우측 근거 패널(자동으로 열림, 위 autoEvidenceOpen
          참고)로 대체한다. 기획서 생성 전(작성 중)에는 그대로 여기서 편집한다. */}
        {!rawLocked && (
          <div className="text-sm">
            <div className="flex items-center justify-between mb-2">
              <button
                type="button"
                onClick={() => setRawNoteOpen(v => !v)}
                className="flex items-center gap-1.5 text-muted-foreground font-medium hover:text-foreground transition-colors"
              >
                <ChevronDown className={cn("w-4 h-4 transition-transform shrink-0", !rawNoteOpen && "-rotate-90")} />
                원본 회의록 / 메모
              </button>
              {canEditRaw && rawDirty && (
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
                onChange={e => canEditRaw && setRawDraft(e.target.value)}
                readOnly={!canEditRaw}
                placeholder="내용이 없습니다."
                title={!canEditRaw ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 수정할 수 있습니다." : undefined}
                className={cn(
                  "w-full h-48 bg-black/5 dark:bg-white/5 border border-border rounded-xl p-4 whitespace-pre-wrap overflow-y-auto text-muted-foreground resize-none focus:outline-none transition-all",
                  !canEditRaw ? "cursor-default" : "focus:ring-2 focus:ring-primary/40"
                )}
              />
            )}
          </div>
        )}

        <p className="text-sm text-muted-foreground font-semibold flex items-center gap-2">
          기획서
          {spec && <span className="text-xs font-mono font-normal text-muted-foreground/70">기획서 번호 {spec.id}</span>}
        </p>
        <div className="border border-border rounded-xl overflow-hidden bg-black/10 dark:bg-black/30 p-4 flex flex-col items-center gap-3">
          {parsedContent ? (
            <div className="doc-scroll w-full max-w-[840px] max-h-[1190px] overflow-y-auto bg-white dark:bg-white">
              <div id="print-area">
                <ProposalTemplate
                  doc={parsedContent}
                  title={note.title} dateLabel={dateLabel}
                  editable={editMode} onChange={setEditDraft}
                  periodEditable={periodEditable} onPeriodChange={handlePeriodChange}
                  evidenceItems={parseEvidenceItems(spec?.evidence_items ?? null)}
                  activeEvidenceKey={targetedEvidenceOpen ? evidenceTarget.sectionKey : undefined}
                  onViewEvidence={showEvidence}
                />
              </div>
            </div>
          ) : (
            <div className="w-full max-w-[840px] bg-white dark:bg-white p-10 text-center text-muted-foreground text-sm">
              {!canGenerate || isPM ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 생성할 수 있습니다." : "AI가 아직 기획서를 생성하지 않았습니다."}
            </div>
          )}
        </div>

        <EvidencePanel
          open={evidencePanelOpen && activeTab === "proposal"}
          onClose={() => { setEvidenceTarget(null); setAutoEvidenceOpen(false); }}
          fullText={note.content ?? ""}
          targetQuotes={targetedEvidenceOpen ? evidenceTarget.quotes : []}
          targetGroups={targetedEvidenceOpen ? evidenceTarget.items : undefined}
          width={evidencePanelWidth}
          onWidthChange={setEvidencePanelWidth}
        />

        <div className="flex flex-wrap justify-end items-center gap-3 pt-2">
          {spec && (
            <div className="flex items-center gap-2 mr-auto shrink-0">
              <button onClick={handlePrint} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors whitespace-nowrap">
                <Printer className="w-3.5 h-3.5" /> PDF 다운로드
              </button>
              <button onClick={handlePptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors whitespace-nowrap">
                <Download className="w-3.5 h-3.5" /> PPTX 다운로드
              </button>
            </div>
          )}

          {!spec && canGenerate && !isPM && (
            <>
              {busy === busyKey("generate") && <SpecGenProgressBar stage={specGenStage} startedAt={specGenStartedAt} />}
              <button
                onClick={onGenerateSpec}
                disabled={busy === busyKey("generate")}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
              >
                {busy === busyKey("generate") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
                {busy === busyKey("generate") ? (specGenStage || "기획서 생성 중…") : "기획서 생성"}
              </button>
            </>
          )}

          {/* 2026-09-10: 팀원 요청으로 추가한 "재생성" 버튼 — analyze 엔드포인트가 이미
            update_or_create라 기존 기획서 위에 덮어써도 백엔드 수정 없이 안전하다. 다만
            검토요청 이후(PENDING_REVIEW/APPROVED)에는 노출하지 않는다 — 승인된 기획서 내용이
            사용자가 인지하지 못한 채 AI 재생성으로 통째로 바뀌면 안 되기 때문(검토요청 버튼과
            같은 조건). "직접수정"으로 손댄 내용도 재생성하면 사라지므로 실행 전 확인창을 띄운다. */}
          {spec && !isPM && canGenerate && (status === "DRAFT" || status === "REJECTED") && (
            <>
              {busy === busyKey("generate") && <SpecGenProgressBar stage={specGenStage} startedAt={specGenStartedAt} />}
              <button
                onClick={() => {
                  if (window.confirm("기획서를 다시 생성하면 현재 내용(직접 수정한 부분 포함)이 AI 결과로 덮어써집니다. 계속하시겠습니까?")) {
                    onGenerateSpec();
                  }
                }}
                disabled={busy === busyKey("generate")}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors disabled:opacity-50 whitespace-nowrap"
              >
                {busy === busyKey("generate") ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                {busy === busyKey("generate") ? (specGenStage || "재생성 중…") : "재생성"}
              </button>
            </>
          )}

          {/* 검토요청은 하단, 승인/반려는 상단 우측 — "직접수정"도 하단에 있어서 사용자
            흐름상 하단에 두는 게 더 자연스럽다는 판단으로 다시 하단으로 내렸다. */}
          {spec && !isPM && canGenerate && (status === "DRAFT" || status === "REJECTED") && (
            <button
              onClick={() => onSubmitReview(spec)}
              disabled={busy === busyKey("submit")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
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
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors whitespace-nowrap"
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
            reqExtractStage={reqExtractStage}
            reqExtractStartedAt={reqExtractStartedAt}
            onAddItem={onAddItem}
            onUpdateItem={onUpdateItem}
            onDeleteItem={onDeleteItem}
            onStatusChange={(statusCode) => onReqDefStatusChange(spec!, reqDef!.id, statusCode)}
            onGenerateTasks={() => onGenerateTasks(spec!, reqDef!.id)}
            generatingTasks={!!reqDef && busy === `reqdef-${reqDef.id}-tasks`}
            generatingStage={!!reqDef && busy === `reqdef-${reqDef.id}-tasks` ? generatingStage : ""}
            generatingStartedAt={!!reqDef && busy === `reqdef-${reqDef.id}-tasks` ? generatingStartedAt : null}
            onRejectClick={() => onRejectReqDef(spec!, reqDef!.id)}
            tasksAlreadyAssigned={tasksForReqDef.length > 0}
            hasUnconfirmedDraft={!!taskDrafts && taskDrafts.length > 0 && taskDraftsReqDefId === reqDef?.id}
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
            scheduleTitle={note.title}
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
                <div className="text-center">
                  <p className="text-sm font-semibold text-muted-foreground">에이전트가 업무를 배분하는 중입니다…</p>
                  {/* 순차 LLM 호출이 여러 개라 1~수 분 걸릴 수 있어(2026-09-14
                      "느리다" 문의 확인), 멈춘 것처럼 보이지 않도록 현재 단계를 보여준다. */}
                  {generatingStage && (
                    <p className="text-xs text-muted-foreground/70 mt-1">{generatingStage}</p>
                  )}
                </div>
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
            scheduleTitle={note.title}
            approvingAll={approvingAllTasks}
            onApproveAll={() => onApproveAllTasks(
              tasksForReqDef.filter(t => t.status_info?.code_id === "PENDING_APPROVAL").map(t => t.id)
            )}
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

function ReasonRow({ techFit, workloadFit, experienceFit, scheduleReason, colSpan = 4 }: { techFit: string | null; workloadFit: string | null; experienceFit: string | null; scheduleReason?: string | null; colSpan?: number }) {
  return (
    <tr className="bg-black/[0.02] dark:bg-white/[0.02]">
      <td colSpan={colSpan} className="px-4 pb-3 pt-0">
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
  drafts, setDrafts, scheduleSummary, packageSplits, planReview, planBriefing, members, confirming, onCancel, onConfirm, scheduleTitle,
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
  scheduleTitle: string;
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
      epicNo: d.epic_no,
      epicTitle: d.epic_title,
    }));

  // 2026-09-17: 원래 정렬이 전혀 없어 백엔드가 담당자를 결정한 순서(우선순위·업무
  // 패키지 크기, 날짜와 무관) 그대로 표에 나열돼 뒤죽박죽으로 보였다(사용자 리포트).
  // 한때 "담당자순"(담당자별 날짜순) 토글도 있었으나, 인접한 업무가 실제로는
  // 무관한데 같은 담당자·비슷한 날짜라는 이유만으로 옆에 붙어 있어 같은 Epic인
  // 것처럼 오해를 낳았다(2026-09-22 사용자 리포트) — Epic 단위(업무순) 하나로
  // 통일한다. Epic을 그 안 업무들의 최소 시작일 오름차순으로 배치하고, Epic
  // 안에서는 시작일 오름차순으로 정렬한다.
  const sortedDrafts = useMemo(() => {
    const byEpic = new Map<string, TaskDraft[]>();
    for (const d of drafts) {
      const key = d.epic_no || "";
      (byEpic.get(key) ?? byEpic.set(key, []).get(key)!).push(d);
    }
    const epicGroups = [...byEpic.values()].sort((a, b) => {
      const minStart = (items: TaskDraft[]) =>
        items.reduce((min, d) => (d.start_date && (!min || d.start_date < min) ? d.start_date : min), "");
      return (minStart(a) || "9999-12-31").localeCompare(minStart(b) || "9999-12-31");
    });
    // 2026-09-22: Task 헤더는 담당자가 없어 start_date가 항상 비어있다 — 날짜만으로
    // 정렬하면 맨 뒤로 밀려 자기 Subtask들보다 아래에 나온다. 헤더를 같은 Epic 안에서
    // 먼저 오게 하고, 그 다음은 기존대로 날짜순.
    const byDate = (a: TaskDraft, b: TaskDraft) => {
      if (a.is_task_header !== b.is_task_header) return a.is_task_header ? -1 : 1;
      return (a.start_date || "9999-12-31").localeCompare(b.start_date || "9999-12-31");
    };
    return epicGroups.flatMap(items => [...items].sort(byDate));
  }, [drafts]);

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
      <div className="pt-2">
        <GanttSection items={ganttItems} title={scheduleTitle} />
      </div>
      <div className="border border-border rounded-xl overflow-hidden overflow-x-auto">
        {/* 아직 "배분 확정"을 누르지 않은 draft 상태임을 강조 — 확정되면 이 화면 자체가
            TaskAssignmentList로 바뀌면서 같이 사라진다(사용자 요청). 표 헤더와 같은
            회색 배경을 그대로 위로 늘려서 표의 일부처럼 보이게 했다. */}
        <div className="px-4 py-2 text-xs font-bold text-center text-amber-600 dark:text-amber-400 bg-black/5 dark:bg-white/5 border-b border-border">
          미리보기 (확정 전)
        </div>
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
            {sortedDrafts.map((d, idx) => {
              // 2026-09-22: Epic이 바뀌는 지점에 구분 행을 넣는다. Epic 헤더가 이미
              // 소속을 보여주므로 업무명 쪽엔 epicLabel을 따로 안 넣는다(중복).
              const showEpicHeader = d.epic_no !== sortedDrafts[idx - 1]?.epic_no;
              const isSubtask = !!d.parent_task_id;
              return (
                <Fragment key={d.unit_id}>
                  {showEpicHeader && (
                    <tr className="bg-primary/5">
                      <td colSpan={4} className="px-4 py-2 text-xs font-bold text-primary">
                        {d.epic_no} · {d.epic_title}
                      </td>
                    </tr>
                  )}
                  {d.is_task_header ? (
                    // 2026-09-22 (사용자 요청): Subtask로 쪼개진 Task 자신은 배정 대상이
                    // 아니라 담당자·적합도·일정 칸이 없다 — 그 하위 Subtask들을 묶는
                    // 제목만 보여준다(estimated_hours는 하위 Subtask 합계, services.py에서
                    // 계산해 내려줌).
                    <tr className="align-top bg-black/[0.015] dark:bg-white/[0.015]">
                      <td className="px-4 py-3" colSpan={4}>
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold">{d.title}</span>
                          <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-muted-foreground font-semibold">
                            {d.estimated_hours ?? "-"}h 합계
                          </span>
                          <span className="text-xs text-muted-foreground">하위 업무로 배정됨 — 이 Task 자체엔 담당자·일정 없음</span>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    <tr className="align-top">
                      <td className="px-4 py-3">
                        {/* Subtask는 들여쓰기+화살표로 표시한다 — Epic으로 이미 실제
                            소속이 묶인 상태라 인접이 우연이 아니다. */}
                        <div className={cn("flex items-start gap-1", isSubtask && "pl-5")}>
                          {isSubtask && <span className="text-muted-foreground/60 text-xs mt-0.5 shrink-0">↳</span>}
                          <TaskTitleCell
                            title={d.title}
                            estimatedHours={d.estimated_hours}
                            techFit={d.tech_fit}
                            featureArea={d.feature_area}
                            expanded={expandedUnitId === d.unit_id}
                            onToggleExpand={() => setExpandedUnitId(v => v === d.unit_id ? null : d.unit_id)}
                          />
                        </div>
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
                  )}
                  {!d.is_task_header && expandedUnitId === d.unit_id && (
                    <ReasonRow techFit={d.tech_fit} workloadFit={d.workload_fit} experienceFit={d.experience_fit} scheduleReason={d.schedule_reason} />
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end gap-3">
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
  tasks, members, isPM, reassigningTaskId, onReassign, scheduleTitle, approvingAll, onApproveAll,
}: {
  tasks: TaskAssignmentDto[]; members: Member[]; isPM: boolean;
  reassigningTaskId: number | null;
  onReassign: (taskId: number, assigneeId: number) => void;
  scheduleTitle: string;
  approvingAll: boolean;
  onApproveAll: () => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // 드롭박스를 바꾸는 즉시 저장되면 실수로 잘못 바꾸기 쉽다는 피드백 — 이 기능 전체가
  // "제안 → 확정" 패턴이니 재배정도 똑같이, 고르기만 하면 우선 화면에만 반영(staged)되고
  // 옆의 "확정" 버튼을 눌러야 실제로 PATCH가 나간다.
  const [pendingReassign, setPendingReassign] = useState<Record<number, number>>({});

  const ganttItems: GanttItem[] = tasks
    .filter(t => t.start_date && t.end_date)
    .map(t => ({
      id: String(t.id), title: t.title, assigneeName: t.assigned_user_name, start: t.start_date!, end: t.end_date!,
      epicNo: t.epic_no, epicTitle: t.epic_title,
    }));

  // 배분 확정 직후엔 전부 PENDING_APPROVAL("배분승인대기")로 시작해서, PM이 projects/[id]
  // 칸반보드에서 개별 승인해야 TASK_APPROVED로 바뀐다(위 상태 배지 주석 참고). 하나라도
  // 아직 승인 전이면 이 배치 전체가 "확정 전" 미리보기 단계임을 표시한다(사용자 요청).
  const hasPendingApproval = tasks.some(t => t.status_info?.code_id === "PENDING_APPROVAL");

  return (
    <div className="space-y-4">
      <CollapsibleSection title="예상 필요 인원">
        <HeadcountSummary assigneeIds={tasks.map(t => t.assigned_user)} members={members} />
      </CollapsibleSection>
      <div className="pt-2">
        <GanttSection items={ganttItems} title={scheduleTitle} />
      </div>
      <div className="border border-border rounded-xl overflow-hidden overflow-x-auto">
        {hasPendingApproval && (
          <div className="px-4 py-2 text-xs font-bold text-center text-amber-600 dark:text-amber-400 bg-black/5 dark:bg-white/5 border-b border-border">
            미리보기 (확정 전)
          </div>
        )}
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-4 py-3 font-bold w-12">번호</th>
              <th className="px-4 py-3 font-bold">업무명 / 배정 근거 <span className="normal-case font-semibold text-muted-foreground/70">(총 {tasks.length}건)</span></th>
              <th className="px-4 py-3 font-bold w-44">담당자</th>
              <th className="px-4 py-3 font-bold w-40">일정</th>
              <th className="px-4 py-3 font-bold w-28">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {tasks.map((t, idx) => (
              <Fragment key={t.id}>
                <tr className="align-top">
                  <td className="px-4 py-3 text-xs font-semibold text-muted-foreground">{idx + 1}</td>
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
                    {/* 배분 확정(TASK_APPROVED) 이후에는 담당자 드롭박스 자체를 비활성화한다 —
                        "확정된 이후에는 담당자 변경이 안 되도록" 해야 한다는 사용자 지적으로
                        수정(이전엔 APPROVED 상태에서도 재배정 드롭박스를 열어뒀었다).
                        2026-09-16: 담당자가 승인 후 진행률을 올려 IN_PROGRESS로 넘어간
                        업무도 같은 이유로 잠가야 한다는 지적, 그리고 업무가 아예 완료(DONE)된
                        경우도 마찬가지라는 지적 — 이미 착수했거나 끝난 업무를 중간에
                        담당자만 바꿔치기하면 안 되므로 IN_PROGRESS/DONE 모두 잠금 대상에
                        추가한다. 확정 전 상태(PENDING_APPROVAL — 자동배정 등 다른 경로로
                        만들어진 업무)만 드롭박스로 담당자를 바꿀 수 있고, 그 뒤엔 읽기
                        전용으로 보여준다.
                        2026-09-16 (잠금 예외): 담당자가 퇴사 처리됐으면 위 잠금 때문에
                        그 업무를 영영 재배정 못 하고 방치하게 된다 — 퇴사한 담당자면
                        상태와 무관하게 드롭박스를 열어준다. */}
                    {isPM && (!["TASK_APPROVED", "IN_PROGRESS", "DONE"].includes(t.status_info?.code_id ?? "") || t.assigned_user_resigned) ? (
                      <div className="flex flex-col gap-1">
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
                        {/* 2026-09-16 (사용자 요청): 재배정하면 원래 AI가 누굴 추천했었는지
                          화면에서 알 수 없어진다는 지적 — 현재 선택(대기 중 선택 포함)이
                          AI 원래 추천과 다를 때만 참고용으로 보여준다. */}
                        {t.original_assigned_user_name &&
                          (pendingReassign[t.id] ?? t.assigned_user) !== t.original_assigned_user && (
                            <p className="text-[11px] text-muted-foreground pl-0.5">
                              AI 추천 담당자: {t.original_assigned_user_name}
                            </p>
                          )}
                        {t.assigned_user_resigned && ["TASK_APPROVED", "IN_PROGRESS", "DONE"].includes(t.status_info?.code_id ?? "") && (
                          <p className="text-[11px] text-amber-500 pl-0.5">
                            담당자가 퇴사 처리되어 재배정이 필요합니다
                          </p>
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
                    {/* 2026-09-16: 프론트가 "배분완료" 같은 문구를 따로 지어내면 실제 DB
                        code_name("배분승인대기")과 어긋나는 사고가 났다(팀 지적) — 화면엔
                        항상 서버가 준 code_name을 그대로 보여준다. 배분 확정 직후 상태는
                        PENDING_APPROVAL("배분승인대기")이고, PM이 개별 승인하면(projects/[id]
                        페이지, 칸반보드) TASK_APPROVED("승인됨")로 바뀐다. */}
                    <span className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold",
                      (t.status_info?.code_id === "DONE" || t.status_info?.code_id === "TASK_APPROVED")
                        ? "bg-emerald-500/10 text-emerald-500" : "bg-orange-500/10 text-orange-500"
                    )}>
                      {t.status_info?.code_name ?? "미지정"}
                    </span>
                  </td>
                </tr>
                {expandedId === t.id && t.assignment_reason && (
                  <ReasonRow
                    techFit={t.assignment_reason.split(" / ")[0] ?? null}
                    workloadFit={t.assignment_reason.split(" / ")[1] ?? null}
                    experienceFit={t.assignment_reason.split(" / ")[2] ?? null}
                    colSpan={5}
                  />
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {/* 2026-09-18 (사용자 요청): 담당자 본인이 /approvals나 칸반보드에서 한 건씩 승인하지
          않아도, 이 문서 화면에서 PM이 PENDING_APPROVAL 건 전체를 한 번에 확정할 수 있어야
          한다 — 백엔드도 이제 PM 승인을 다시 허용한다. 전부 승인되면(hasPendingApproval=false)
          이 버튼과 위 미리보기 배지가 함께 사라진다. */}
      {isPM && hasPendingApproval && (
        <div className="flex justify-end">
          <button
            onClick={onApproveAll}
            disabled={approvingAll}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {approvingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            배분 확정
          </button>
        </div>
      )}
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
// 원문 보기 패널이 사용할 섹션별 인용문을 정규화한다. 백엔드가 어느 명명 규칙으로
// 저장하든(스네이크케이스 원본 필드명이든, 프론트와 동일한 카멜케이스든) 받아들이도록
// 두 가지 키 형태를 모두 매핑한다 — 포맷이 확정되면 필요 없는 쪽은 정리해도 된다.
const EVIDENCE_KEY_ALIASES: Record<string, keyof ProposalEvidence> = {
  overview: "projectOverview", projectOverview: "projectOverview",
  problem_definition: "problemDefinition", problemDefinition: "problemDefinition",
  goals: "projectGoals", projectGoals: "projectGoals",
  target_users: "target", target: "target",
  key_features: "features", features: "features",
  tech_stack: "techStackConstraints", techStackConstraints: "techStackConstraints",
  final_decisions: "finalDecisions", finalDecisions: "finalDecisions",
};

export function parseEvidenceItems(raw: string | null): ProposalEvidenceEntries {
  if (!raw || !raw.trim()) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const result: ProposalEvidenceEntries = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const mappedKey = EVIDENCE_KEY_ALIASES[key];
      if (!mappedKey || !value || typeof value !== "object" || Array.isArray(value)) continue;
      const entry = value as Record<string, unknown>;
      const quotes = Array.isArray(entry.quotes)
        ? entry.quotes.filter((quote): quote is string => typeof quote === "string" && quote.trim().length > 0)
        : [];
      const items = Array.isArray(entry.items)
        ? entry.items.flatMap((item): ProposalEvidenceItem[] => {
          if (!item || typeof item !== "object" || Array.isArray(item)) return [];
          const candidate = item as Record<string, unknown>;
          if (typeof candidate.title !== "string" || !candidate.title.trim() || !Array.isArray(candidate.quotes)) return [];
          const itemQuotes = candidate.quotes.filter((quote): quote is string => typeof quote === "string" && quote.trim().length > 0);
          return itemQuotes.length > 0 ? [{ title: candidate.title.trim(), quotes: itemQuotes }] : [];
        })
        : undefined;
      if (quotes.length > 0 || (items && items.length > 0)) result[mappedKey] = { quotes, items };
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

// 2026-09-15: "업무 일정 보기"를 자유 위치 막대 대신 실제 스프레드시트 UI(AG Grid)로
// 바꿨다 — 엑셀 다운로드(exportGanttExcel)와 같은 모양(담당자·날짜별 칸)을 화면에서도
// 그대로 보이게 하자는 요청. 열은 작업명 | 담당자 | 날짜 1일당 1칸이고, 업무 하나당
// 한 행(담당자 셀 병합은 하지 않음 — 같은 담당자라도 각 업무를 바로 구분할 수 있게).
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
  // 36px짜리 좁은 날짜 칸에 "9/15"를 다 넣으면 잘려 보인다 — 일(day) 숫자만
  // 표시하고, 전체 날짜는 헤더 툴팁으로 확인하게 한다.
  const fmtHeader = (d: Date) => `${d.getDate()}`;
  const fmtFullDate = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;
  const todayIndex = Math.round((toLocalMidnight(new Date().toISOString()) - rangeStartMs) / DAY_MS);

  // 담당자별로 묶어 첫 시작일 순으로 정렬 — 셀 병합은 안 해도 같은 담당자 업무가
  // 이어서 보이도록 순서만 유지한다(엑셀 다운로드와 동일한 정렬 규칙).
  const byAssignee = new Map<string, GanttItem[]>();
  items.forEach(i => {
    if (!byAssignee.has(i.assigneeName)) byAssignee.set(i.assigneeName, []);
    byAssignee.get(i.assigneeName)!.push(i);
  });
  const groups = Array.from(byAssignee.entries())
    .map(([name, personItems]) => {
      const sorted = [...personItems].sort((a, b) => toLocalMidnight(a.start) - toLocalMidnight(b.start));
      return { name, items: sorted, firstStart: toLocalMidnight(sorted[0].start) };
    })
    .sort((a, b) => a.firstStart - b.firstStart);

  type Row = { title: string; assigneeName: string; epicLabel: string; startIdx: number; endIdx: number };
  const rowData: Row[] = groups.flatMap(({ items: personItems }) =>
    personItems.map(item => ({
      title: item.title,
      assigneeName: item.assigneeName,
      // 2026-09-22: 어느 Epic 소속 업무인지 여기서도 보이게 — 번호가 없으면(예:
      // 예전 데이터) 제목만, 제목도 없으면 빈 칸으로 둔다.
      epicLabel: [item.epicNo, item.epicTitle].filter(Boolean).join(" · "),
      startIdx: dayIndexOf(item.start),
      endIdx: dayIndexOf(item.end),
    }))
  );

  const BAR_COLOR = "#4f46e5";

  // 2026-09-15: 업무 배정 자체는(백엔드 scheduler.py) 평일만 계산하는데, 화면의
  // 막대는 시작~종료일 사이 달력일을 통째로 칠해서 주말도 진행 중인 것처럼
  // 보였다 — 주말은 막대 색을 칠하지 않고(실제로 일이 없는 날), 날짜 숫자만
  // 빨간 글씨로 구분해서 보여준다.
  const dayColumns: ColDef<Row>[] = days.map((d, i) => {
    const isWeekend = d.getDay() === 0 || d.getDay() === 6;
    return {
      headerName: fmtHeader(d),
      headerTooltip: fmtFullDate(d),
      colId: `day_${i}`,
      // 2026-09-15: 34px에 패딩만 줄여서는 "15"/"23" 같은 두 자리 날짜가 여전히
      // 잘려 보였다(헤더 셀 안쪽에 정렬/리사이즈용 wrapper가 더 있어서 padding:0
      // 만으로는 부족) — 칸을 40px로 넓히고 그 wrapper까지 함께 덮어써서
      // 실제로 두 자리가 다 보이게 한다.
      width: 40,
      resizable: false,
      sortable: false,
      suppressMovable: true,
      // 매달 1일은 경계를 굵게 표시해 월이 바뀌는 지점을 알 수 있게 한다.
      headerClass: cn(
        "ag-header-cell-day",
        isWeekend && "ag-header-cell-weekend",
        i === todayIndex && "ag-header-cell-today",
        d.getDate() === 1 && "ag-header-cell-month-start"
      ),
      // 2026-09-15: 막대가 없는 빈 날짜 칸은 구분선이 없어 어느 날짜인지 눈으로
      // 따라가기 어렵다는 요청 — 칸마다 세로선을 그어 색칠 여부와 무관하게
      // 매 날짜 경계가 보이게 한다.
      cellClass: "ag-cell-day-col",
      cellStyle: (params: { data?: Row }) => {
        if (isWeekend) return undefined; // 주말은 절대 막대 색을 칠하지 않는다.
        return params.data && params.data.startIdx <= i && i <= params.data.endIdx
          ? { backgroundColor: BAR_COLOR }
          : undefined;
      },
    };
  });

  // 날짜 칸 위에 월(月) 그룹 헤더를 한 줄 더 얹는다 — 같은 달인 날짜끼리 하나의
  // 그룹으로 묶어 AG Grid의 2단 헤더로 표시한다.
  const dayGroups: ColGroupDef<Row>[] = [];
  days.forEach((d, i) => {
    const label = `${d.getMonth() + 1}월`;
    const last = dayGroups[dayGroups.length - 1];
    if (last && last.headerName === label) {
      (last.children as ColDef<Row>[]).push(dayColumns[i]);
    } else {
      dayGroups.push({ headerName: label, children: [dayColumns[i]] });
    }
  });

  const columnDefs: (ColDef<Row> | ColGroupDef<Row>)[] = [
    { headerName: "Epic", field: "epicLabel", pinned: "left", width: 160, cellClass: "text-xs text-muted-foreground" },
    { headerName: "작업명", field: "title", pinned: "left", width: 220, cellClass: "text-xs font-semibold" },
    { headerName: "담당자", field: "assigneeName", pinned: "left", width: 110, cellClass: "text-xs" },
    ...dayGroups,
  ];

  return (
    // 2026-09-15: domLayout="autoHeight"로 두면 AG Grid가 세로 스크롤을 포기하고
    // 행 수만큼 계속 늘어나 버려서(가로 스크롤만 되고 세로는 바깥 모달에 맡기는
    // 구조), 행이 많으면 모달 밖으로 잘려 보이는 문제가 있었다 — h-full + 기본
    // domLayout(normal)으로 바꿔 AG Grid 자신이 가로·세로 스크롤을 전부 갖게 한다.
    <div className="h-full gantt-scroll-area">
      <style>{`
        /* AG Grid 기본 헤더 셀(.ag-header-cell)이 좌우 16px씩 패딩을 갖고 있어서
           40px짜리 좁은 날짜 칸은 실제 글자 공간이 8px밖에 안 남아 "15" 같은
           두 자리가 통째로 잘렸다 — 진짜 원인은 이 바깥쪽 패딩이었다. */
        .ag-header-cell-day { padding: 0 !important; }
        .ag-header-cell-day .ag-header-cell-comp-wrapper,
        .ag-header-cell-day .ag-header-cell-label { padding: 0 !important; margin: 0 !important; justify-content: center !important; }
        .ag-header-cell-day .ag-header-cell-text { font-size: 11px; }
        .ag-header-cell-today { background-color: #dce7ff !important; }
        .ag-header-cell-month-start { border-left: 2px solid #94a3b8 !important; }
        .ag-header-cell-weekend .ag-header-cell-text { color: #dc2626; }
        /* 막대가 없는 빈 날짜 칸도 세로 구분선이 보이도록 — 색칠 여부와 무관하게
           모든 날짜 칸에 적용된다. */
        .ag-cell-day-col { border-right: 1px solid #e2e8f0; }
        /* 전역 CSS가 모든 스크롤바를 지워서(globals.css) 실제로는 되는 가로/세로
           스크롤이 안 보였다(사용자 보고) — 이 그리드 안쪽만 다시 보이게 한다.
           2026-09-16: 헤더 위에 별도 보조 스크롤바를 추가했다가, 그 wrapper가
           AG Grid의 height:100% 연쇄를 끊어서 세로 스크롤이 아예 깨지는(하단이
           잘린 채 휠로도 안 내려가는) 회귀가 생겨 되돌렸다 — 원래처럼 이 div
           바로 아래 AG Grid 하나만 두고, 스크롤바는 그리드 자체 것만 보이게 한다. */
        .gantt-scroll-area .ag-body-horizontal-scroll-viewport,
        .gantt-scroll-area .ag-body-vertical-scroll-viewport {
          scrollbar-width: thin !important;
          -ms-overflow-style: auto !important;
        }
        .gantt-scroll-area .ag-body-horizontal-scroll-viewport::-webkit-scrollbar,
        .gantt-scroll-area .ag-body-vertical-scroll-viewport::-webkit-scrollbar {
          display: block !important;
          width: 10px;
          height: 10px;
        }
        .gantt-scroll-area .ag-body-horizontal-scroll-viewport::-webkit-scrollbar-thumb,
        .gantt-scroll-area .ag-body-vertical-scroll-viewport::-webkit-scrollbar-thumb {
          background: rgba(0, 0, 0, 0.25);
          border-radius: 6px;
        }
      `}</style>
      <AgGridReact<Row>
        theme={themeQuartz}
        columnDefs={columnDefs}
        rowData={rowData}
        headerHeight={28}
        groupHeaderHeight={22}
        rowHeight={28}
        suppressCellFocus
        // 2026-09-16: 이 prop을 생략해도 AG Grid 문서상 기본값은 "normal"이지만,
        // 실제로 행이 많을 때(44건+) 세로 스크롤이 전혀 동작하지 않고 그리드가
        // 내용 높이만큼 계속 늘어나 모달 밖으로 잘리는 문제가 재현됐다(사용자
        // 보고) — AG Grid 내부 CSS(.ag-root-wrapper.ag-layout-normal{height:100%})가
        // domLayout에 대응하는 클래스에 의존하는데, prop을 명시하지 않으면 이
        // 클래스가 붙지 않을 수 있어 보인다. 명시적으로 지정해 확실히 한다.
        domLayout="normal"
        // 2026-09-16: 전역 CSS가 스크롤바를 전부 숨겨서(globals.css) AG Grid가
        // 내부적으로 "네이티브 스크롤바 두께 = 0"으로 측정해, 스크롤 영역
        // 계산에 그 공간을 아예 반영하지 않고 있었다 — 위 <style>에서 스크롤바를
        // 다시 보이게 만들자, 그 실제 두께(10px)만큼 맨 아래 행/맨 오른쪽 열이
        // 항상(끝까지 스크롤해도) 가려 잘려 보이는 문제가 생겼다(사용자 보고,
        // alwaysShow* 옵션만으로는 해결 안 됨 — 그건 "숨기지 마라"용이지
        // "계산에 반영해라"용이 아니다). scrollbarWidth로 실제 두께를 직접
        // 알려주면 AG Grid가 그만큼을 스크롤 가능 영역 계산에 넣어서, 끝까지
        // 스크롤했을 때 마지막 행/열이 스크롤바에 가리지 않고 온전히 보인다.
        alwaysShowVerticalScroll
        alwaysShowHorizontalScroll
        scrollbarWidth={10}
      />
    </div>
  );
}

// "업무 일정 보기" 버튼 + 모달 — 인라인으로 두니 페이지 스크롤과 간트 자체의 가로
// 스크롤이 겹쳐서 조작이 불편하다는 피드백에 따라, 카드 안에는 트리거 버튼만 두고
// 실제 간트는 화면 대부분을 차지하는 큰 모달 안에서 보여준다(NewDocumentModal과
// 동일한 오버레이 스타일). 모달이 넓어진 만큼 날짜도 더 잘 읽힌다.
function GanttSection({ items, title }: { items: GanttItem[]; title: string }) {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  if (items.length === 0) return null;

  const handleExportExcel = async () => {
    setExporting(true);
    try {
      const { exportGanttExcel } = await import("@/lib/exportGanttExcel");
      await exportGanttExcel(items, title);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-sm font-semibold"
      >
        <Maximize2 className="w-4 h-4 text-primary" />
        업무 일정 보기
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 backdrop-blur-sm" onClick={() => setOpen(false)}>
          <div
            // 2026-09-15: "더 크게 해달라"는 요청 — max-w-6xl(72rem)에서
            // 뷰포트의 96%까지 쓰도록 넓혔다. 2026-09-16: 마지막 행이 스크롤을
            // 끝까지 내려도 half-row 정도 잘려 보이는 AG Grid 스크롤 계산
            // 문제(원인 특정 전)의 실질적 영향을 줄이기 위해, 스크롤 자체가
            // 덜 필요하도록 뷰포트를 거의 꽉 채우게 더 키운다.
            className="bg-background rounded-2xl shadow-2xl w-full max-w-[99vw] h-[97vh] border border-border flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center p-5 border-b border-border shrink-0">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <CalendarIcon className="w-5 h-5 text-primary" />
                업무 일정
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportExcel}
                  disabled={exporting}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-xs font-bold hover:bg-black/5 dark:hover:bg-white/5 transition-colors disabled:opacity-50"
                >
                  {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileSpreadsheet className="w-3.5 h-3.5" />}
                  Excel 다운로드
                </button>
                <button
                  onClick={() => setOpen(false)}
                  className="text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 p-2 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            {/* min-h-0: flex 자식은 기본 min-height:auto라 h-full을 줘도 내용이
                넘치는 만큼 부모를 그냥 뚫고 나가 버린다 — 이거 없으면 AG Grid가
                자기 높이를 못 정하고 계속 늘어난다. 세로/가로 스크롤은 이제
                AG Grid 자신이 담당하므로(GanttChart 참고) 여기서는 overflow를
                주지 않는다(주면 스크롤이 두 군데로 겹쳐서 조작이 헷갈린다). */}
            <div className="p-5 flex-1 min-h-0">
              <GanttChart items={items} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function RequirementSection({
  spec, reqDef, isPM, canGenerate, busy, onCreate, onExtract, reqExtractStage, reqExtractStartedAt, onAddItem, onUpdateItem, onDeleteItem, onStatusChange,
  onGenerateTasks, generatingTasks, generatingStage, generatingStartedAt, onRejectClick, tasksAlreadyAssigned, hasUnconfirmedDraft,
}: {
  spec: SpecDto; reqDef: ReqDefDto | null; isPM: boolean;
  // 기획서 탭과 동일한 규칙 — 이 문서(회의록)를 시작한 작성자 본인만 요구사항정의서를
  // 생성/수정/삭제/검토요청할 수 있다. 예전엔 isPM만 봐서, PM이 아니기만 하면 다른
  // 사람이 시작한 문서의 요구사항정의서도 마음대로 건드릴 수 있는 문제가 있었다.
  canGenerate: boolean;
  busy: string | null;
  onCreate: () => void;
  onExtract: (specId: number, reqDefId: number) => void;
  reqExtractStage: string;
  reqExtractStartedAt: number | null;
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string; order: number; priority_code: string | null }) => void;
  onUpdateItem: (reqDefId: number, itemId: number, patch: { req_name: string; description: string; priority_code?: string | null }) => void;
  onDeleteItem: (reqDefId: number, itemId: number) => void;
  // REJECTED는 사유 입력 모달(onRejectClick)을 거쳐서만 일어난다 — 상태만 바로 바꾸는
  // 경로를 남겨두면 사유 없이 반려하는 길이 다시 생긴다.
  onStatusChange: (statusCode: "PENDING_REVIEW" | "APPROVED") => void;
  onGenerateTasks: () => void;
  generatingTasks: boolean;
  // 2026-09-14: 순차 LLM 호출 여러 개라 1~수 분 걸릴 수 있어(폴링 진행 중에만
  // 값이 있음), 버튼 옆에 현재 단계를 보여줘 멈춘 것처럼 보이지 않게 한다.
  generatingStage: string;
  generatingStartedAt: number | null;
  onRejectClick: () => void;
  // 이미 배분을 확정한 뒤에는 "업무 배분 실행" 버튼을 완전히 숨긴다 — PM이 요구사항정의서
  // 탭으로 돌아왔을 때 버튼이 그대로 남아있으면 실수로 다시 눌러 기존 배정을 통째로
  // 덮어쓸 위험이 있다(사용자 요청 — 재배분이 필요하면 업무배분 탭에서 별도로 처리).
  tasksAlreadyAssigned: boolean;
  // 아직 확정하지 않은 draft가 이 요구사항정의서용으로 이미 나와있는 상태 — 확정 전에
  // 다시 누르면 검토 중인 draft가 새 결과로 덮어써질 수 있어 비활성화한다(확정 후
  // 숨기는 tasksAlreadyAssigned와 별개 — 확정 전에도 재클릭을 막아야 한다는 사용자 요청).
  hasUnconfirmedDraft: boolean;
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
          <div className="flex items-center gap-3">
            {creating && <ReqExtractProgressBar stage={reqExtractStage} startedAt={reqExtractStartedAt} />}
            <button
              onClick={onCreate}
              disabled={creating}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              {creating ? (reqExtractStage || "생성 중…") : "요구사항 정의서 생성"}
            </button>
          </div>
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
      <div className="flex items-center justify-between flex-wrap gap-3">
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
          {/* heyzzabi2와 동일 — 요구사항정의서가 승인되면 PM이 다음 단계(업무분배)로
              넘어갈 업무를 AI로 자동 추출·배정할 수 있다. 이미 확정된 배정이 있으면
              버튼 자체를 숨긴다(사용자 요청) — 재배분은 업무배분 탭에서만. */}
          {reqStatus === "APPROVED" && isPM && tasksAlreadyAssigned && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
              <CheckCircle2 className="w-3 h-3" /> 업무 배분 완료 — 업무배분 탭에서 확인
            </span>
          )}
          {reqStatus === "APPROVED" && isPM && !tasksAlreadyAssigned && (
            <div className="flex items-center gap-3">
              {generatingTasks && <TaskGenProgressBar stage={generatingStage} startedAt={generatingStartedAt} />}
              <button
                onClick={onGenerateTasks}
                disabled={generatingTasks || hasUnconfirmedDraft}
                title={hasUnconfirmedDraft ? "이미 검토 중인 배분 초안이 있습니다. 업무배분 탭에서 확정하거나 확인해주세요." : undefined}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
              >
                {generatingTasks ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5" />}
                {generatingTasks ? (generatingStage || "배분 진행 중…") : "업무 배분 실행"}
              </button>
            </div>
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
            <div className="flex flex-wrap justify-end items-center gap-3 pt-2">
              <div className="flex items-center gap-2 mr-auto shrink-0">
                <button onClick={handleReqSpecExcel} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors whitespace-nowrap">
                  <FileSpreadsheet className="w-3.5 h-3.5" /> Excel 다운로드
                </button>
                <button onClick={handleReqSpecPptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors whitespace-nowrap">
                  <Download className="w-3.5 h-3.5" /> PPTX 다운로드
                </button>
              </div>
              {!isPM && canGenerate && !tasksAlreadyAssigned && (reqStatus === "DRAFT" || reqStatus === "REJECTED" || reqStatus === null) && (
                <>
                  {extracting && <ReqExtractProgressBar stage={reqExtractStage} startedAt={reqExtractStartedAt} />}
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
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors disabled:opacity-50 whitespace-nowrap"
                  >
                    {extracting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                    {extracting ? (reqExtractStage || "재생성 중…") : "재생성"}
                  </button>
                </>
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
