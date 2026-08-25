"use client";

import { useEffect, useState, useMemo, Fragment } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  FileText, Plus, Bot, Loader2, Send, CheckCircle2, XCircle,
  AlertCircle, Clock, RotateCcw, MessageSquare, X, FolderKanban,
  Download, Printer, Trash2, Save, Pencil, ChevronDown, Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { NewDocumentModal } from "@/components/projects/NewDocumentModal";
import { ProposalTemplate } from "@/components/documents/ProposalTemplate";
import { ReqSpecTemplate } from "@/components/documents/ReqSpecTemplate";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import { exportReqSpecPptx } from "@/lib/exportReqSpecPptx";
import { exportReqSpecExcel } from "@/lib/exportReqSpecExcel";
import { parseProposalDoc, parseReqSpecDoc } from "@/lib/documentTemplates";
import { TaskAssignmentPanel } from "@/components/documents/TaskAssignmentPanel";
import { AgentBadge } from "@/components/ui/AgentBadge";

type DocType = "proposal" | "reqSpec";
type PipelineTab = DocType | "taskAssignment";

type ProjectDocument = {
  id: string;
  title: string;
  rawContent: string | null;
  proposalContent: string | null;
  reqSpecContent: string | null;
  proposalStatus: string;
  proposalRejectReason: string | null;
  reqSpecStatus: string;
  reqSpecRejectReason: string | null;
  meetingDate: string | null;
  updatedAt: string;
};

const STATUS_META: Record<string, { label: string; className: string; icon: any }> = {
  DRAFT: { label: "초안", className: "bg-muted text-muted-foreground", icon: FileText },
  PENDING_REVIEW: { label: "검토 요청중", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  APPROVED: { label: "승인됨", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
  REJECTED: { label: "반려됨", className: "bg-red-500/10 text-red-500", icon: XCircle },
};

// 검토요청(PENDING_REVIEW) 중이거나 이미 승인(APPROVED)돼 다음 단계의 근거가 된 문서는 삭제하면 안 된다.
// 검토요청 전(DRAFT)이거나 반려(REJECTED)된 상태 — 즉 아직 아무 데도 걸려있지 않은 상태에서만 삭제 가능.
const isDocDeletable = (doc: ProjectDocument) =>
  [doc.proposalStatus, doc.reqSpecStatus].every(s => s === "DRAFT" || s === "REJECTED");

const TAB_LABEL: Record<DocType, string> = { proposal: "기획서", reqSpec: "요구사항정의서" };
const PIPELINE_TAB_LABEL: Record<PipelineTab, string> = { proposal: "기획서", reqSpec: "요구사항정의서", taskAssignment: "업무 배분" };
const TASK_ASSIGN_META = {
  NOT_GENERATED: { label: "미생성", className: "bg-muted text-muted-foreground", icon: FileText },
  NEEDS_ASSIGNMENT: { label: "배분 필요", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  ASSIGNED: { label: "배분완료", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
} as const;
const CONTENT_FIELD: Record<DocType, "proposalContent" | "reqSpecContent"> = { proposal: "proposalContent", reqSpec: "reqSpecContent" };
const STATUS_FIELD: Record<DocType, "proposalStatus" | "reqSpecStatus"> = { proposal: "proposalStatus", reqSpec: "reqSpecStatus" };
const REASON_FIELD: Record<DocType, "proposalRejectReason" | "reqSpecRejectReason"> = { proposal: "proposalRejectReason", reqSpec: "reqSpecRejectReason" };

export default function DocumentsPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const searchParams = useSearchParams();

  const [project, setProject] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTabState] = useState<PipelineTab>("proposal");
  const setActiveTab = (tab: PipelineTab) => setActiveTabState(tab);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  // 문서가 지금 파이프라인의 어느 단계에 있는지 — 목록 미리보기의 파이프라인 점, 상단 탭의
  // 진행 표시, "문서를 고르면 그 문서의 현재 단계가 첫 화면으로 보인다"에 전부 이 값을 쓴다.
  const stageOf = (doc: ProjectDocument): PipelineTab => {
    if (doc.reqSpecStatus === "APPROVED") return "taskAssignment";
    if (doc.proposalStatus === "APPROVED") return "reqSpec";
    return "proposal";
  };
  // 목록에서 문서를 고르면(직접 클릭이든, 생성 직후 자동이든) 항상 "그 문서가 지금 있는 단계"를
  // 첫 화면으로 보여준다 — 예전엔 마지막으로 보던 탭(전역 상태)이 그대로 유지돼서, 업무분배 탭을
  // 보다가 아직 기획서 단계인 다른 문서를 고르면 뜬금없는 화면이 나오는 문제가 있었다.
  const selectDoc = (doc: ProjectDocument) => {
    setSelectedDocId(doc.id);
    setActiveTab(stageOf(doc));
  };

  // 히스토리 등 다른 화면에서 "문서생성에서 열기"로 넘어올 때 ?docId=...&tab=... 쿼리로
  // 특정 문서·탭을 바로 열어준다. localStorage로 복원한 탭보다 이 쪽이 우선한다(방금 클릭한 의도이므로).
  useEffect(() => {
    const docIdParam = searchParams.get("docId");
    const tabParam = searchParams.get("tab") as PipelineTab | null;
    if (docIdParam) setSelectedDocId(docIdParam);
    if (tabParam === "proposal" || tabParam === "reqSpec" || tabParam === "taskAssignment") setActiveTabState(tabParam);
  }, [searchParams]);
  const [newDocModalOpen, setNewDocModalOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // action key currently in flight
  const [rejectModal, setRejectModal] = useState<{ docId: string; type: DocType } | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [docFilter, setDocFilter] = useState<"all" | "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED">("all");

  // preferredId가 있으면 그 프로젝트를 바로 보여준다(예: 문서 작성 모달에서 새 프로젝트를 만든 직후) —
  // 없으면 기존처럼 가장 최근(첫 번째) 프로젝트를 기본으로 본다(단일 프로젝트 전제).
  const fetchProject = async (preferredId?: string) => {
    setLoading(true);
    try {
      if (preferredId) {
        const detailRes = await fetch(`/api/projects/${preferredId}`);
        const detail = await detailRes.json();
        if (detail.success) { setProject(detail.data); return; }
      }
      // 예전엔 목록 조회 → 첫 프로젝트 id로 상세 조회 2단계였다 — 원격 DB 왕복이 하나 늘 때마다
      // 체감 지연이 커서(/api/projects/current 참고) 단일 요청으로 합쳤다.
      const res = await fetch("/api/projects/current");
      const detail = await res.json();
      if (detail.success) setProject(detail.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProject(); }, []);

  // PM이 직접 생성하는 문서는 검토 없이 곧장 APPROVED로 넘어가므로(아래 handleGenerate의
  // autoApprove 로직 참고), 목록에 DRAFT 단계로 남아있는 문서는 전부 아직 검토 요청 전인
  // 다른 팀원의 작업 중 문서다. PM이 할 수 있는 액션이 없는 상태라 굳이 목록에 섞여있을
  // 필요가 없어서 PM 화면에서는 제외한다(작성자 본인에게는 계속 보임).
  const allDocuments: ProjectDocument[] = project?.documents ?? [];
  const isVisibleToViewer = (d: ProjectDocument) => {
    if (!isPM) return true;
    const stage = stageOf(d);
    // stage가 "taskAssignment"라는 것 자체가 이미 reqSpecStatus === APPROVED라는 뜻이라
    // (stageOf 정의 참고) 그 경우도 reqSpecStatus 기준으로 판단하면 항상 DRAFT가 아니게 된다.
    const status = stage === "proposal" ? d.proposalStatus : d.reqSpecStatus;
    const content = stage === "proposal" ? d.proposalContent : d.reqSpecContent;
    // 아직 AI가 아무 내용도 생성하지 않은 새 문서는 "남이 검토 요청 전인 초안"이 아니라
    // PM 본인이 방금 만들어서 이제 막 생성 버튼을 눌러야 하는 문서다 — content 유무로
    // 구분하지 않으면 PM이 새 문서를 만들자마자 목록에서 사라져버린다(실제 버그 보고됨).
    if (!content) return true;
    return status !== "DRAFT";
  };
  const documents: ProjectDocument[] = allDocuments.filter(isVisibleToViewer);
  const hiddenDraftCount = allDocuments.length - documents.length;
  const selectedDoc = useMemo(
    () => documents.find(d => d.id === selectedDocId) ?? documents[0] ?? null,
    [documents, selectedDocId]
  );

  useEffect(() => {
    if (!selectedDocId && documents.length > 0) selectDoc(documents[0]);
  }, [documents, selectedDocId]);

  const patchDoc = (docId: string, patch: Partial<ProjectDocument>) => {
    setProject((prev: any) => ({
      ...prev,
      documents: prev.documents.map((d: ProjectDocument) => d.id === docId ? { ...d, ...patch } : d),
    }));
  };

  const handleGenerate = async (doc: ProjectDocument, type: DocType) => {
    setBusy(`${doc.id}-generate-${type}`);
    try {
      // PM이 직접 에이전트를 실행하면 자기 자신에게 검토요청을 보내는 게 의미가 없으므로 바로 승인 처리한다.
      // 일반유저가 실행하면 지금처럼 PM 검토가 필요하다.
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, autoApprove: isPM }),
      });
      const data = await res.json();
      if (res.ok) {
        const resultStatus = isPM ? "APPROVED" : "DRAFT";
        if (type === "proposal") {
          patchDoc(doc.id, {
            proposalContent: JSON.stringify(data.content),
            proposalStatus: resultStatus,
            proposalRejectReason: null,
          });
        } else {
          patchDoc(doc.id, {
            reqSpecContent: JSON.stringify(data.content),
            reqSpecStatus: resultStatus,
            reqSpecRejectReason: null,
          });
        }
      } else {
        alert(data.error || "생성 중 오류가 발생했습니다.");
      }
    } catch {
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const handleSubmitReview = async (doc: ProjectDocument, type: DocType) => {
    setBusy(`${doc.id}-submit-${type}`);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}/submit-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type }),
      });
      const data = await res.json();
      if (data.success) patchDoc(doc.id, { [STATUS_FIELD[type]]: "PENDING_REVIEW" } as Partial<ProjectDocument>);
      else alert(data.error || "검토 요청 실패");
    } finally {
      setBusy(null);
    }
  };

  const handleApprove = async (doc: ProjectDocument, type: DocType) => {
    setBusy(`${doc.id}-approve-${type}`);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type }),
      });
      const data = await res.json();
      if (data.success) patchDoc(doc.id, { [STATUS_FIELD[type]]: "APPROVED", [REASON_FIELD[type]]: null } as Partial<ProjectDocument>);
    } finally {
      setBusy(null);
    }
  };

  const handleReject = async () => {
    if (!rejectModal || !rejectReason.trim()) return;
    const { docId, type } = rejectModal;
    setBusy(`${docId}-reject-${type}`);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${docId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, reason: rejectReason }),
      });
      const data = await res.json();
      if (data.success) {
        patchDoc(docId, { [STATUS_FIELD[type]]: "REJECTED", [REASON_FIELD[type]]: rejectReason } as Partial<ProjectDocument>);
        setRejectModal(null);
        setRejectReason("");
      }
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteDoc = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${deleteTarget.id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        setProject((prev: any) => ({
          ...prev,
          documents: prev.documents.filter((d: ProjectDocument) => d.id !== deleteTarget.id),
        }));
        // 선택된 문서가 삭제된 경우 선택 해제 → useEffect가 남은 첫 번째 문서를 자동 선택
        if (selectedDocId === deleteTarget.id) setSelectedDocId(null);
        setDeleteTarget(null);
      } else {
        alert(data.error || "삭제에 실패했습니다.");
      }
    } finally {
      setDeleting(false);
    }
  };

  const handleSaveRawContent = async (doc: ProjectDocument, rawContent: string) => {
    setBusy(`${doc.id}-save-raw`);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rawContent }),
      });
      const data = await res.json();
      if (data.success) {
        patchDoc(doc.id, { rawContent });
      } else {
        alert(data.error || "저장에 실패했습니다.");
      }
    } catch {
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 반려된 기획서/요구사항정의서를 AI 재생성 없이 직접 고쳐서 저장 — 일반유저는 재생성과 마찬가지로
  // DRAFT로 돌아가 다시 검토요청해야 하고, PM이 직접 고친 거라면(자기 자신에게 검토요청할 필요가
  // 없으므로) 바로 승인 상태로 확정된다. 반려 사유는 둘 다 지워진다.
  const handleSaveDocContent = async (doc: ProjectDocument, type: DocType, content: string) => {
    setBusy(`${doc.id}-save-content-${type}`);
    const resultStatus = isPM ? "APPROVED" : "DRAFT";
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          [CONTENT_FIELD[type]]: content,
          [STATUS_FIELD[type]]: resultStatus,
          [REASON_FIELD[type]]: null,
        }),
      });
      const data = await res.json();
      if (data.success) {
        patchDoc(doc.id, {
          [CONTENT_FIELD[type]]: content,
          [STATUS_FIELD[type]]: resultStatus,
          [REASON_FIELD[type]]: null,
        } as Partial<ProjectDocument>);
      } else {
        alert(data.error || "저장에 실패했습니다.");
      }
    } catch {
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 승인된 요구사항정의서를 근거로 업무를 자동 추출 — 여기서 만들어진 업무들이 "업무분배" 탭에 뜬다.
  // 반려→직접수정→재승인 흐름을 거치면 이 버튼을 다시 누를 수 있는 상태로 돌아오므로, 이미 이
  // 문서에서 뽑아둔 업무가 있으면 재추출이 무엇을 바꾸는지 먼저 알려준다(API가 실제 교체/보존은 처리함).
  const handleGenerateTasks = async (doc: ProjectDocument) => {
    const existingCount = (project?.tasks ?? []).filter((t: any) => t.sourceDocumentId === doc.id).length;
    if (existingCount > 0) {
      const proceed = confirm(
        `이미 이 요구사항정의서에서 추출된 업무 ${existingCount}건이 있습니다.\n아직 배정 전(대기)인 업무는 새 내용으로 교체되고, 이미 진행 중이거나 완료된 업무는 그대로 유지됩니다.\n계속할까요?`
      );
      if (!proceed) return;
    }

    setBusy(`${doc.id}-tasks-reqSpec`);
    try {
      const res = await fetch(`/api/projects/${project.id}/documents/${doc.id}/extract-tasks`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        await fetchProject(project.id);
        setActiveTab("taskAssignment");
        if (data.staleTasks?.length > 0) {
          alert(`이미 진행 중이거나 완료된 업무 ${data.staleTasks.length}건은 예전 요구사항 기준 그대로 남아있습니다. 필요하면 업무분배 탭에서 직접 확인해주세요.`);
        }
      } else {
        alert(data.error || "업무 생성에 실패했습니다.");
      }
    } catch {
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <FolderKanban className="w-10 h-10 text-muted-foreground/30" />
        <p className="text-muted-foreground">
          {isPM ? "아직 프로젝트가 없습니다. 먼저 프로젝트를 생성해주세요." : "아직 프로젝트가 없습니다. PM에게 프로젝트 생성을 요청해주세요."}
        </p>
        {isPM && (
          <Link href="/project/new" className="inline-block mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold hover:bg-primary/90 transition-colors">
            첫 프로젝트 만들기
          </Link>
        )}
      </div>
    );
  }

  // 업무분배 단계는 문서 자체 상태값이 없어 배분 진행도로 배지를 만든다 — 목록 미리보기와
  // 상세 패널 진입 시 둘 다 이 함수로 통일해서 계산 방식이 갈라지지 않게 한다.
  const taskAssignMetaFor = (doc: ProjectDocument) => {
    const docTasks = (project.tasks ?? []).filter((t: any) => t.sourceDocumentId === doc.id);
    return docTasks.length === 0
      ? TASK_ASSIGN_META.NOT_GENERATED
      : docTasks.every((t: any) => t.assigneeId)
      ? TASK_ASSIGN_META.ASSIGNED
      : TASK_ASSIGN_META.NEEDS_ASSIGNMENT;
  };
  // 목록 행에는 "그 문서가 지금 있는 단계"의 배지를 보여준다(예전엔 전역 activeTab 기준이라,
  // 업무분배 탭을 보고 있으면 아직 기획서 단계인 문서도 업무분배 배지가 붙어 헷갈렸다).
  const stageMeta = (doc: ProjectDocument, stage: PipelineTab): { label: string; className: string; icon: any } =>
    stage === "taskAssignment" ? taskAssignMetaFor(doc) : (STATUS_META[doc[STATUS_FIELD[stage]]] ?? STATUS_META.DRAFT);
  // 필터 칩은 문서 상태 어휘(초안/검토요청중/승인됨/반려됨)로 노출한다 — 업무분배 단계는 거기
  // 들어서는 조건 자체가 "요구사항정의서 승인"이므로 "승인됨"으로 자연스럽게 묶인다.
  const docStatusKey = (doc: ProjectDocument): "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" => {
    const stage = stageOf(doc);
    return stage === "taskAssignment" ? "APPROVED" : (doc[STATUS_FIELD[stage]] as any);
  };
  // "배분완료"는 문서 상태(docStatusKey)와 별개 축이라 승인됨과 겹치는데(배분완료 문서는 항상
  // 승인됨이기도 함), 승인됨 안에서 각 카드 배지(미생성/배분 필요/배분완료)로 이미 구분되니
  // 필터 칩까지 따로 둘 필요는 없다는 판단으로 뺌(중복이라는 피드백) — 배지 자체는 유지.
  // PM 목록에는 DRAFT 문서 자체가 안 뜨니(위 isVisibleToViewer) "초안" 칩은 항상 0건이라 의미가 없다 — PM에게는 숨긴다.
  const DOC_FILTERS = [
    { key: "all" as const, label: "전체" },
    ...(isPM ? [] : [{ key: "DRAFT" as const, label: "초안" }]),
    { key: "PENDING_REVIEW" as const, label: "검토요청중" },
    { key: "APPROVED" as const, label: "승인됨" },
    { key: "REJECTED" as const, label: "반려됨" },
  ];
  const docFilterCounts = {
    all: documents.length,
    DRAFT: documents.filter(d => docStatusKey(d) === "DRAFT").length,
    PENDING_REVIEW: documents.filter(d => docStatusKey(d) === "PENDING_REVIEW").length,
    APPROVED: documents.filter(d => docStatusKey(d) === "APPROVED").length,
    REJECTED: documents.filter(d => docStatusKey(d) === "REJECTED").length,
  };
  const filteredDocuments = docFilter === "all" ? documents : documents.filter(d => docStatusKey(d) === docFilter);

  const PIPELINE_STEPS: PipelineTab[] = ["proposal", "reqSpec", "taskAssignment"];
  const stepDone = (doc: ProjectDocument | null, step: PipelineTab): boolean => {
    if (!doc) return false;
    if (step === "proposal") return doc.proposalStatus === "APPROVED";
    if (step === "reqSpec") return doc.reqSpecStatus === "APPROVED";
    return false; // 업무분배는 "완료"라는 개념 자체가 없어(계속 추가 배분 가능) 항상 false
  };

  return (
    <div className="w-full space-y-6 animate-in fade-in duration-500">
      {/* Header + Pipeline stepper — 기획서 → 요구사항정의서 → 업무분배가 실제로 하나로
          이어지는 파이프라인임을 보이게: 완료된 단계는 체크, 지금 선택한 문서가 있는 단계는
          강조 링, 아직 안 온 단계는 흐리게. 탭 자체는 항상 클릭 가능(과거 단계도 열람 목적). */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-8 flex-wrap">
          <div className="flex items-center">
            {PIPELINE_STEPS.map((step, i) => {
              const done = stepDone(selectedDoc, step);
              const isDocStage = selectedDoc ? stageOf(selectedDoc) === step : false;
              const isViewed = activeTab === step;
              const prevDone = i > 0 ? stepDone(selectedDoc, PIPELINE_STEPS[i - 1]) : false;
              return (
                <Fragment key={step}>
                  {i > 0 && <div className={cn("h-0.5 w-6 md:w-10 rounded-full transition-colors", prevDone ? "bg-emerald-500/50" : "bg-black/10 dark:bg-white/10")} />}
                  <button
                    onClick={() => setActiveTab(step)}
                    className={cn(
                      "flex items-center gap-2 pb-1 px-1 text-base font-medium transition-colors border-b-2",
                      isViewed ? "border-primary text-primary font-bold" : "border-transparent text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span className={cn(
                      "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 transition-colors",
                      done ? "bg-emerald-500 text-white"
                        : isDocStage ? "bg-primary text-primary-foreground ring-4 ring-primary/20"
                        : "bg-black/10 dark:bg-white/10 text-muted-foreground"
                    )}>
                      {done ? <CheckCircle2 className="w-3 h-3" /> : i + 1}
                    </span>
                    {PIPELINE_TAB_LABEL[step]}
                  </button>
                </Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* 우측 상세 패널의 너비가 문서마다 안의 콘텐츠(표/긴 텍스트) 크기에 따라 밀려서 달라지지 않도록,
          1fr 대신 minmax(0,1fr)로 트랙 크기를 컨테이너 폭에 고정하고 내부에서만 overflow 스크롤되게 한다 */}
      <div className="grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-6 items-start">
        {/* Document list */}
        <div className="glass rounded-2xl border border-border p-4 space-y-3">
          <button
            onClick={() => setNewDocModalOpen(true)}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" /> 새 회의록 / 문서
          </button>

          {documents.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {DOC_FILTERS.map(f => (
                <button
                  key={f.key}
                  onClick={() => setDocFilter(f.key)}
                  className={cn(
                    "flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all",
                    docFilter === f.key ? "bg-primary/15 text-primary" : "bg-black/5 dark:bg-white/5 text-muted-foreground hover:text-foreground"
                  )}
                >
                  {f.label}
                  <span className="text-[9px] opacity-70">{docFilterCounts[f.key]}</span>
                </button>
              ))}
            </div>
          )}

          <div className="space-y-2">
            {documents.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                {hiddenDraftCount > 0
                  ? <>팀원이 작성 중인 초안 {hiddenDraftCount}건이 있지만, 아직 검토 요청 전이라 여기 표시되지 않습니다.</>
                  : <>등록된 문서가 없습니다.<br />회의록을 등록하세요.</>}
              </p>
            ) : filteredDocuments.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">해당하는 문서가 없습니다.</p>
            ) : (
              filteredDocuments.map(doc => {
                const stage = stageOf(doc);
                const meta = stageMeta(doc, stage);
                const Icon = meta.icon;
                return (
                  <div
                    key={doc.id}
                    className={cn(
                      "group w-full flex items-start gap-1 p-3 rounded-xl border transition-colors",
                      selectedDoc?.id === doc.id
                        ? "border-primary/50 bg-primary/5"
                        : "border-transparent hover:bg-black/5 dark:hover:bg-white/5"
                    )}
                  >
                    <button onClick={() => selectDoc(doc)} className="flex-1 min-w-0 text-left">
                      <p className="font-semibold text-sm truncate mb-1.5">{doc.title}</p>
                      {/* 미니 파이프라인 — 이 문서가 지금 3단계 중 어디에 있는지 한눈에 */}
                      <div className="flex items-center gap-1 mb-1.5">
                        {PIPELINE_STEPS.map((step, i) => (
                          <Fragment key={step}>
                            {i > 0 && <div className={cn("h-px w-3", stepDone(doc, PIPELINE_STEPS[i - 1]) ? "bg-emerald-500/40" : "bg-black/10 dark:bg-white/10")} />}
                            <div
                              title={PIPELINE_TAB_LABEL[step]}
                              className={cn(
                                "w-1.5 h-1.5 rounded-full shrink-0",
                                step === stage ? "bg-primary ring-2 ring-primary/25" : stepDone(doc, step) ? "bg-emerald-500" : "bg-black/10 dark:bg-white/15"
                              )}
                            />
                          </Fragment>
                        ))}
                      </div>
                      <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
                        <Icon className="w-3 h-3" /> {meta.label}
                      </span>
                      {/* 제목이 겹치는 문서가 많아 구분하기 어려우니 날짜를 함께 보여준다 — 회의 날짜가
                          있으면 그걸(문서 내용과 의미가 맞음), 없으면(과거/시드 데이터) 최근 수정일로 대체 */}
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {new Date(doc.meetingDate ?? doc.updatedAt).toLocaleDateString("ko-KR")}
                      </p>
                    </button>
                    {isDocDeletable(doc) ? (
                      <button
                        onClick={() => setDeleteTarget({ id: doc.id, title: doc.title })}
                        title="문서 삭제"
                        className="shrink-0 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all text-muted-foreground hover:text-red-400 hover:bg-red-500/10"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    ) : (
                      // 휴지통 아이콘을 그냥 흐리게만 하면 hover했을 때 여전히 눌러도 될 것처럼 보이고,
                      // 이유는 title 툴팁뿐이라 터치기기에선 아예 안 보인다 — 자물쇠 아이콘으로 바꿔서
                      // hover 없이도(터치에서도) "지금 잠겨있다"는 상태 자체가 보이게 한다
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

        {/* Detail / preview panel */}
        <div className="glass rounded-2xl border border-border p-6 min-h-[500px]">
          {!selectedDoc ? (
            <div className="h-full flex items-center justify-center text-muted-foreground text-sm py-20">
              왼쪽에서 문서를 선택하거나 새로 등록해주세요.
            </div>
          ) : (
            // 세 탭을 조건부 렌더링(삼항연산자로 갈아끼우기)하면 탭을 옮길 때마다 컴포넌트가 완전히
            // unmount됐다가 다시 mount되면서 그 안의 로컬 상태(예: 업무분배 탭의 AI 추천 결과 draft,
            // 아직 저장 안 한 원본 회의록 편집 등)가 통째로 날아간다 — 실제로 이 문제로 AI 추천 배정
            // 결과가 사라지는 버그가 보고됐다. 세 패널을 전부 항상 mount해두고 CSS로만 숨겨서,
            // 안 보이는 탭의 상태도 그대로 유지되게 한다.
            <>
              <div className={activeTab === "taskAssignment" ? "" : "hidden"}>
                <TaskAssignmentPanel
                  doc={selectedDoc}
                  tasks={(project.tasks ?? []).filter((t: any) => t.sourceDocumentId === selectedDoc.id)}
                  isPM={isPM}
                  projectId={project.id}
                  onRefresh={fetchProject}
                />
              </div>
              <div className={activeTab === "proposal" ? "" : "hidden"}>
                <DocDetail
                  doc={selectedDoc}
                  type="proposal"
                  isPM={isPM}
                  busy={busy}
                  onGenerate={() => handleGenerate(selectedDoc, "proposal")}
                  onSubmitReview={() => handleSubmitReview(selectedDoc, "proposal")}
                  onApprove={() => handleApprove(selectedDoc, "proposal")}
                  onReject={() => setRejectModal({ docId: selectedDoc.id, type: "proposal" })}
                  onSaveRawContent={(rawContent) => handleSaveRawContent(selectedDoc, rawContent)}
                  onSaveDocContent={(content) => handleSaveDocContent(selectedDoc, "proposal", content)}
                  onGenerateTasks={() => handleGenerateTasks(selectedDoc)}
                />
              </div>
              <div className={activeTab === "reqSpec" ? "" : "hidden"}>
                <DocDetail
                  doc={selectedDoc}
                  type="reqSpec"
                  isPM={isPM}
                  busy={busy}
                  onGenerate={() => handleGenerate(selectedDoc, "reqSpec")}
                  onSubmitReview={() => handleSubmitReview(selectedDoc, "reqSpec")}
                  onApprove={() => handleApprove(selectedDoc, "reqSpec")}
                  onReject={() => setRejectModal({ docId: selectedDoc.id, type: "reqSpec" })}
                  onSaveRawContent={(rawContent) => handleSaveRawContent(selectedDoc, rawContent)}
                  onSaveDocContent={(content) => handleSaveDocContent(selectedDoc, "reqSpec", content)}
                  onGenerateTasks={() => handleGenerateTasks(selectedDoc)}
                />
              </div>
            </>
          )}
        </div>
      </div>

      {newDocModalOpen && (
        <NewDocumentModal
          defaultProjectId={project?.id}
          onClose={async (createdProjectId, createdDocId) => {
            setNewDocModalOpen(false);
            await fetchProject(createdProjectId);
            // 방금 만든 문서를 곧바로 선택 상태로 — 안 그러면 목록은 갱신됐는데 화면엔 계속
            // 이전에 보던(엉뚱한) 문서가 남아있어서 "내가 만든 게 어디 갔지" 하고 헷갈리게 된다.
            if (createdDocId) { setSelectedDocId(createdDocId); setActiveTab("proposal"); }
          }}
        />
      )}

      {rejectModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <RotateCcw className="w-5 h-5" /> 반려 사유 입력
              </h3>
              <button onClick={() => setRejectModal(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
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
              <button onClick={() => setRejectModal(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
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

      {/* 문서 삭제 확인 모달 */}
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
                onClick={handleDeleteDoc}
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
    </div>
  );
}

function DocDetail({
  doc, type, isPM, busy, onGenerate, onSubmitReview, onApprove, onReject, onSaveRawContent, onSaveDocContent, onGenerateTasks,
}: {
  doc: ProjectDocument; type: DocType; isPM: boolean; busy: string | null;
  onGenerate: () => void;
  onSubmitReview: () => void; onApprove: () => void; onReject: () => void;
  onSaveRawContent: (rawContent: string) => void;
  onSaveDocContent: (content: string) => void;
  onGenerateTasks: () => void;
}) {
  const content = doc[CONTENT_FIELD[type]];
  const status = doc[STATUS_FIELD[type]];
  const reason = doc[REASON_FIELD[type]];
  // API가 상태값을 검증하지 않아 이론상 STATUS_META에 없는 값이 저장될 수 있다(QA에서 실제로 발견됨) —
  // 그런 경우에도 화면이 죽지 않도록 DRAFT로 방어적으로 대체한다.
  const meta = STATUS_META[status] ?? STATUS_META.DRAFT;
  const canGenerateReqSpec = type === "reqSpec" ? doc.proposalStatus === "APPROVED" : true;
  const dateLabel = new Date(doc.updatedAt).toLocaleDateString("ko-KR");

  const busyKey = (action: string) => `${doc.id}-${action}-${type}`;

  const handlePrint = () => window.print();

  const handlePptx = async () => {
    if (type === "proposal") {
      const parsed = parseProposalDoc(doc.proposalContent);
      if (!parsed) return;
      await exportProposalPptx(parsed, doc.title);
    } else {
      const parsed = parseReqSpecDoc(doc.reqSpecContent);
      if (!parsed) return;
      await exportReqSpecPptx(parsed, doc.title);
    }
  };

  const handleExcel = async () => {
    const parsed = parseReqSpecDoc(doc.reqSpecContent);
    if (!parsed) return;
    await exportReqSpecExcel(parsed, doc.title);
  };

  // 원본 회의록/메모는 문서를 옮겨다녀도(doc.id 변경) 이전 문서의 미저장 편집분이 남지 않도록
  // doc.id가 바뀔 때마다 로컬 편집 상태를 서버 값으로 리셋한다
  const [rawDraft, setRawDraft] = useState(doc.rawContent ?? "");
  useEffect(() => { setRawDraft(doc.rawContent ?? ""); }, [doc.id]);
  const rawDirty = rawDraft !== (doc.rawContent ?? "");
  const rawSaving = busy === busyKey("save-raw");

  // 반려된 문서를 AI 재생성 없이 직접 고쳐 쓰는 모드 — 문서를 옮기면 편집 중이던 내용은 버린다.
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<any>(null);
  useEffect(() => { setEditMode(false); setEditDraft(null); }, [doc.id, type]);
  const editSaving = busy === busyKey("save-content");

  const startEdit = () => {
    setEditDraft(type === "proposal" ? parseProposalDoc(content) : parseReqSpecDoc(content));
    setEditMode(true);
  };
  const saveEdit = () => {
    if (!editDraft) return;
    onSaveDocContent(JSON.stringify(editDraft));
    setEditMode(false);
  };

  // parseProposalDoc/parseReqSpecDoc은 형식이 손상된 문서(레거시 포맷 등)에서 null을 반환할 수
  // 있다 — 과거 이 경우를 `!`로 무시하다가 화면이 죽은 적이 있어(PROJECT_STATUS.md 참고),
  // 여기서 한 번만 계산해 null이면 아래에서 안전한 폴백 문구를 보여준다.
  const parsedContent = editMode ? editDraft : (type === "proposal" ? parseProposalDoc(content) : parseReqSpecDoc(content));
  // reqSpec 탭의 "기획서 원본" 참고 박스에서 쓴다 — 위와 별개로 항상 doc.proposalContent 기준.
  const parsedProposalRef = parseProposalDoc(doc.proposalContent);

  // 잠긴 상태에서도 내용 자체는 볼 수 있어야 하므로, 수정은 막되 펼쳐서 전체를 확인하는 건 허용한다.
  // 기본은 접어서(h-20) 자리를 적게 차지하다가, 필요할 때만 펼친다(h-64) — 수정 가능 여부와는 별개.
  const [rawLockedExpanded, setRawLockedExpanded] = useState(false);
  useEffect(() => { setRawLockedExpanded(false); }, [doc.id]);

  // 검토요청(PENDING_REVIEW) 이후 ~ 승인(APPROVED) 상태에서는 원본 회의록을 잠근다 —
  // 이미 그 내용을 근거로 기획서가 만들어져 검토에 들어간 상태라, 뒤에서 원본이 바뀌면 안 된다.
  // PM이 반려하면 다시 풀려서 수정할 수 있고, 그때 기획서 에이전트도 다시 실행할 수 있다.
  const rawLocked = status === "PENDING_REVIEW" || status === "APPROVED";

  // 요구사항정의서 탭 상단에 보여줄 기획서 원본 참고 박스 — 기본은 접어두고 필요할 때만 펼친다
  const [proposalRefOpen, setProposalRefOpen] = useState(false);
  useEffect(() => { setProposalRefOpen(false); }, [doc.id]);
  const proposalMeta = STATUS_META[doc.proposalStatus] ?? STATUS_META.DRAFT;
  const REQSPEC_BLOCK_MESSAGE: Record<string, string> = {
    DRAFT: "기획서가 아직 작성 중입니다. 기획서를 검토요청하고 승인받아야 요구사항정의서를 생성할 수 있습니다.",
    PENDING_REVIEW: "기획서가 아직 검토요청 중입니다. PM 승인 후 요구사항정의서를 생성할 수 있습니다.",
    REJECTED: "기획서가 반려되었습니다. 기획서를 다시 작성해 승인받아야 합니다.",
    APPROVED: "",
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-lg">{doc.title}</h2>
        <span className={cn("inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold", meta.className)}>
          <meta.icon className="w-3.5 h-3.5" /> {meta.label}
        </span>
      </div>

      {/* 반려 사유는 제일 먼저 눈에 띄어야(뭘 고쳐야 하는지 알아야 원본을 고치든 직접수정을 하든 할 테니) 맨 위에 둔다 */}
      {reason && status === "REJECTED" && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div><span className="font-semibold">반려 사유:</span> {reason}</div>
        </div>
      )}

      {/* 요구사항정의서 탭에서는 원본 회의록 대신, 이 문서가 근거로 삼는 기획서 원본을 접었다 폈다 볼 수 있게 보여준다.
          기획서가 아직 승인 전이면 지금 상태(작성중/검토중/반려)를 배지로 함께 보여준다. */}
      {type === "reqSpec" && (
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
            <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", proposalMeta.className)}>
              <proposalMeta.icon className="w-3 h-3" /> {proposalMeta.label}
            </span>
          </button>
          {proposalRefOpen && (
            <div className="mt-2 border border-border rounded-xl overflow-hidden max-h-64 overflow-y-auto bg-black/5 dark:bg-black/20">
              {parsedProposalRef ? (
                <ProposalTemplate doc={parsedProposalRef} title={doc.title} dateLabel={dateLabel} />
              ) : (
                <div className="p-6 text-center text-muted-foreground text-xs">기획서 내용이 없습니다.</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 기획서 탭: 검토요청(PENDING_REVIEW) ~ 승인(APPROVED) 사이에는 원본이 잠기고 작게 줄어든다 —
          이미 그 내용으로 기획서가 만들어져 검토 중이므로 뒤에서 바뀌면 안 되기 때문. PM이 반려하면
          다시 풀리고 원래 크기(h-64)로 돌아와 수정할 수 있다. 직접 수정 가능하도록 textarea로 작성됨 —
          원본 내용과 달라졌을 때만 저장 버튼이 활성화된다. */}
      {type === "proposal" && (
        <div className="text-sm">
          <div className="flex items-center justify-between mb-2">
            <p className="text-muted-foreground font-medium flex items-center gap-1.5">
              원본 회의록 / 메모
              {rawLocked && (
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
                  <Lock className="w-3 h-3" /> 검토 중에는 수정할 수 없습니다
                </span>
              )}
            </p>
            {rawLocked ? (
              <button
                type="button"
                onClick={() => setRawLockedExpanded(v => !v)}
                className="flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
              >
                <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", !rawLockedExpanded && "-rotate-90")} />
                {rawLockedExpanded ? "접기" : "펼쳐보기"}
              </button>
            ) : rawDirty && (
              <button
                onClick={() => onSaveRawContent(rawDraft)}
                disabled={rawSaving}
                className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 disabled:opacity-50 transition-colors"
              >
                {rawSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                저장
              </button>
            )}
          </div>
          <textarea
            value={rawDraft}
            onChange={e => !rawLocked && setRawDraft(e.target.value)}
            readOnly={rawLocked}
            placeholder="내용이 없습니다."
            className={cn(
              "w-full bg-black/5 dark:bg-white/5 border border-border rounded-xl p-4 whitespace-pre-wrap overflow-y-auto text-muted-foreground resize-none focus:outline-none transition-all",
              rawLocked
                ? cn("cursor-default", rawLockedExpanded ? "h-64" : "h-20")
                : "h-64 focus:ring-2 focus:ring-primary/40"
            )}
          />
        </div>
      )}

      <div className="border border-border rounded-xl overflow-hidden">
        <div className="max-h-[520px] overflow-y-auto bg-black/5 dark:bg-black/20">
          {content && parsedContent ? (
            <div id="print-area">
              {type === "proposal" ? (
                <ProposalTemplate
                  doc={parsedContent}
                  title={doc.title} dateLabel={dateLabel}
                  editable={editMode} onChange={setEditDraft}
                />
              ) : (
                <ReqSpecTemplate
                  doc={parsedContent}
                  title={doc.title} dateLabel={dateLabel}
                  editable={editMode} onChange={setEditDraft}
                />
              )}
            </div>
          ) : content ? (
            <div className="p-10 text-center text-muted-foreground text-sm">
              문서 내용을 표시할 수 없습니다. 형식이 손상되었을 수 있습니다.
            </div>
          ) : (
            <div className="p-10 text-center text-muted-foreground text-sm">
              {!canGenerateReqSpec
                ? REQSPEC_BLOCK_MESSAGE[doc.proposalStatus] || "기획서가 승인되면 요구사항정의서를 생성할 수 있습니다."
                : `AI가 아직 ${TAB_LABEL[type]}를 생성하지 않았습니다.`}
            </div>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex justify-end items-center gap-3 pt-2">
        {content && (
          <div className="flex items-center gap-2 mr-auto">
            <button onClick={handlePrint} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <Printer className="w-3.5 h-3.5" /> PDF 다운로드
            </button>
            <button onClick={handlePptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
              <Download className="w-3.5 h-3.5" /> PPTX 다운로드
            </button>
            {type === "reqSpec" && (
              <button onClick={handleExcel} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
                <Download className="w-3.5 h-3.5" /> EXCEL 다운로드
              </button>
            )}
          </div>
        )}

        {/* 문서를 누가 만들었든(PM 포함) 그 자리에서 바로 AI 에이전트를 실행할 수 있어야 하므로 역할 제한을 두지 않는다 */}
        {!content && canGenerateReqSpec && (
          <button
            onClick={onGenerate}
            disabled={busy === busyKey("generate")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("generate") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
            {type === "proposal" ? "기획서 생성" : "요구사항정의서 생성"}
            <AgentBadge agent={type} />
          </button>
        )}

        {content && !isPM && status === "DRAFT" && (
          <button
            onClick={onSubmitReview}
            disabled={busy === busyKey("submit")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("submit") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            검토요청
          </button>
        )}

        {content && status === "REJECTED" && !editMode && (
          <>
            <button
              onClick={startEdit}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors"
            >
              <Pencil className="w-4 h-4" /> 직접 수정
            </button>
            <button
              onClick={onGenerate}
              disabled={busy === busyKey("generate")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500/10 text-red-400 border border-red-500/30 text-sm font-bold hover:bg-red-500/20 disabled:opacity-50"
            >
              {busy === busyKey("generate") ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
              {type === "proposal" ? "기획서 재생성" : "요구사항정의서 재생성"}
              <AgentBadge agent={type} />
            </button>
          </>
        )}

        {status === "REJECTED" && editMode && (
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
              저장하고 다시 검토요청
            </button>
          </>
        )}

        {content && !isPM && status === "PENDING_REVIEW" && (
          <span className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-muted text-muted-foreground text-sm font-bold">
            <Clock className="w-4 h-4" /> 요청완료
          </span>
        )}

        {content && isPM && status === "PENDING_REVIEW" && (
          <>
            <button
              onClick={onReject}
              disabled={busy === busyKey("reject")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-bold hover:bg-red-500/20 disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" /> 반려
            </button>
            <button
              onClick={onApprove}
              disabled={busy === busyKey("approve")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 text-white text-sm font-bold hover:bg-emerald-600 disabled:opacity-50"
            >
              {busy === busyKey("approve") ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              승인
            </button>
          </>
        )}

        {/* 요구사항정의서가 승인되면 PM이 다음 단계(업무분배)로 넘어갈 업무를 자동 추출할 수 있다 */}
        {type === "reqSpec" && status === "APPROVED" && isPM && (
          <button
            onClick={onGenerateTasks}
            disabled={busy === busyKey("tasks")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("tasks") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
            업무 배분 실행
            <AgentBadge agent="taskAssign" />
          </button>
        )}

      </div>
    </div>
  );
}
