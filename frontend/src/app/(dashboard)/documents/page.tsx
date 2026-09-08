"use client";

import { useEffect, useState, useMemo, Fragment } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import {
  FileText, Plus, Bot, Loader2, Send, CheckCircle2, XCircle,
  AlertCircle, Clock, RotateCcw, MessageSquare, X, FolderKanban,
  Download, Printer, Trash2, Save, Pencil, Lock, ChevronDown, Briefcase,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { NewDocumentModal } from "@/components/projects/NewDocumentModal";
import { ProposalTemplate } from "@/components/documents/ProposalTemplate";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import type { ProposalDoc } from "@/lib/documentTemplates";
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
  user_scenarios: string | null;
  tech_stack: string | null;
  final_decisions: string | null;
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
  id: number;
  req_code: string;
  req_name: string;
  description: string;
  category?: string;
  difficulty?: string;
};

type ReqDefDto = {
  id: number;
  spec: number;
  project: number;
  title: string;
  version: string;
  description?: string;
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

const STATUS_META: Record<BareStatus, { label: string; className: string; icon: any }> = {
  DRAFT: { label: "초안", className: "bg-muted text-muted-foreground", icon: FileText },
  PENDING_REVIEW: { label: "검토 요청중", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  APPROVED: { label: "승인됨", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
  REJECTED: { label: "반려됨", className: "bg-red-500/10 text-red-500", icon: XCircle },
};

function specToProposalDoc(spec: SpecDto): ProposalDoc {
  return {
    projectOverview: spec.overview ?? "",
    problemDefinition: spec.problem_definition ?? "",
    target: spec.target_users ?? "",
    features: spec.key_features ?? "",
    userScenario: spec.user_scenarios ?? "",
    techStackConstraints: spec.tech_stack ?? "",
    finalDecisions: spec.final_decisions ?? "",
    projectPeriod: { start: spec.period_start ?? "", end: spec.period_end ?? "" },
  };
}

function proposalDocToPatch(doc: ProposalDoc) {
  return {
    overview: doc.projectOverview,
    problem_definition: doc.problemDefinition,
    target_users: doc.target,
    key_features: doc.features,
    user_scenarios: doc.userScenario,
    tech_stack: doc.techStackConstraints,
    final_decisions: doc.finalDecisions,
    period_start: doc.projectPeriod?.start || null,
    period_end: doc.projectPeriod?.end || null,
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
  const [loading, setLoading] = useState(true);
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<PipelineTab>("proposal");
  const [newDocModalOpen, setNewDocModalOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<{ specId: number } | null>(null);
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
  // 문서를 고르면(직접 클릭이든, 등록 직후 자동이든) 항상 "그 문서가 지금 있는 단계"를
  // 첫 화면으로 보여준다 — heyzzabi2와 동일한 동작.
  const selectNote = (note: NoteDto) => {
    setSelectedNoteId(note.id);
    setActiveTab(stageOf(note.spec_documents[0] ?? null));
  };
  // 지금 보던 탭이 승인 등으로 잠기게 되면(방금 승인한 경우 포함) 자동으로 다음 단계로 넘어간다.
  useEffect(() => {
    if (!selectedNote) return;
    const spec = selectedNote.spec_documents[0] ?? null;
    if (stepDone(spec, activeTab)) setActiveTab(stageOf(spec));
  }, [selectedNote?.id, selectedNote?.spec_documents[0]?.status_code, activeTab]);

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
      await apiFetch(`/api/meetings/specs/${rejectTarget.specId}/reject/`, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      await refetchNote(selectedNote.id);
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
      setToastMessage(`요구사항 항목 ${itemCount}건이 추출되었습니다`);
    } catch (err: any) {
      setErrorToast(err.message || "요구사항 추출에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  };

  // 백엔드 requirements/urls.py에는 <reqDefId>/items/ 같은 중첩 경로가 없다(items/ 하나뿐,
  // req_def는 body로 받음) — 중첩 경로로 호출하면 404가 난다(직접 재현해서 확인).
  const handleAddItem = async (reqDefId: number, item: { req_code: string; req_name: string; description: string }) => {
    setBusy(`reqdef-${reqDefId}-additem`);
    try {
      const newItem = await apiFetch<ReqItemDto>(`/api/requirements/items/`, {
        method: "POST",
        body: JSON.stringify({ req_def: reqDefId, ...item }),
      });
      setReqDefs(prev => prev.map(r => r.id === reqDefId ? { ...r, items: [...r.items, newItem] } : r));
      setToastMessage("요구사항 항목이 추가되었습니다");
    } catch (err: any) {
      setErrorToast(err.message || "항목 추가에 실패했습니다.");
    } finally {
      setBusy(null);
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
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold">문서생성</h1>
          <p className="text-sm text-muted-foreground mt-1">
            회의록을 기반으로 기획서를 작성하고 검토·승인합니다.
          </p>
        </div>
      </div>

      {/* Pipeline stepper — 기획서 → 요구사항정의서 → 업무배분이 하나로 이어지는
          파이프라인임을 보여준다(heyzzabi2 참고). 완료된 단계는 잠금(초록 자물쇠),
          지금 선택한 문서가 있는 단계는 강조 링, 탭 자체는 항상 클릭 가능(과거 열람용). */}
      <div className="flex items-center">
        {PIPELINE_STEPS.map((step, i) => {
          const done = stepDone(activeSpec, step);
          const isDocStage = selectedNote ? stageOf(activeSpec) === step : false;
          const isViewed = activeTab === step;
          const prevDone = i > 0 ? stepDone(activeSpec, PIPELINE_STEPS[i - 1]) : false;
          const locked = done;
          return (
            <Fragment key={step}>
              {i > 0 && <div className={cn("h-0.5 w-6 md:w-10 rounded-full transition-colors", prevDone ? "bg-emerald-500/50" : "bg-black/10 dark:bg-white/10")} />}
              <button
                onClick={() => !locked && setActiveTab(step)}
                disabled={locked}
                title={locked ? "승인이 완료되어 더 이상 열람할 수 없습니다." : undefined}
                className={cn(
                  "flex items-center gap-2 pb-1 px-1 text-base font-medium transition-colors border-b-2",
                  locked
                    ? "border-transparent text-muted-foreground/50 cursor-not-allowed"
                    : isViewed ? "border-primary text-primary font-bold" : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                <span className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 transition-colors",
                  done ? "bg-emerald-500 text-white"
                    : isDocStage ? "bg-primary text-primary-foreground ring-4 ring-primary/20"
                    : "bg-black/10 dark:bg-white/10 text-muted-foreground"
                )}>
                  {locked ? <Lock className="w-3 h-3" /> : i + 1}
                </span>
                {PIPELINE_TAB_LABEL[step]}
              </button>
            </Fragment>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-6 items-start">
        {/* Document list */}
        <div className="glass rounded-2xl border border-border p-4 space-y-3">
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
                      <p className="font-semibold text-sm truncate mb-1.5">{note.title}</p>
                      {/* 미니 파이프라인 — 이 문서가 지금 3단계 중 어디에 있는지 한눈에 */}
                      <div className="flex items-center gap-1 mb-1.5">
                        {PIPELINE_STEPS.map((step, i) => (
                          <Fragment key={step}>
                            {i > 0 && <div className={cn("h-px w-3", stepDone(spec, PIPELINE_STEPS[i - 1]) ? "bg-emerald-500/40" : "bg-black/10 dark:bg-white/10")} />}
                            <div
                              title={PIPELINE_TAB_LABEL[step]}
                              className={cn(
                                "w-1.5 h-1.5 rounded-full shrink-0",
                                step === stageOf(spec) ? "bg-primary ring-2 ring-primary/25" : stepDone(spec, step) ? "bg-emerald-500" : "bg-black/10 dark:bg-white/15"
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
              onReject={(spec) => setRejectTarget({ specId: spec.id })}
              onCreateReqDef={(spec) => handleCreateReqDef(selectedNote, spec)}
              onExtractItems={handleExtractItems}
              onAddItem={handleAddItem}
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
  onCreateReqDef, onExtractItems, onAddItem,
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
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string }) => void;
}) {
  const status = bareStatus(spec);
  const meta = STATUS_META[status];
  const canGenerate = String(note.created_by) === currentUserId;
  const dateLabel = new Date(note.updated_at).toLocaleDateString("ko-KR");

  const busyKey = (action: string) => `${note.id}-${action}`;

  const [rawDraft, setRawDraft] = useState(note.content ?? "");
  useEffect(() => { setRawDraft(note.content ?? ""); }, [note.id, note.content]);
  const rawDirty = rawDraft !== (note.content ?? "");
  const rawSaving = busy === busyKey("save-raw");
  const rawLocked = !!spec;
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
          <h2 className="font-bold text-lg">{note.title}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            작성자 {note.created_by_name || "알 수 없음"}
            {String(note.created_by) === currentUserId && <span className="text-primary font-medium"> (나)</span>}
          </p>
        </div>
        <span className={cn("inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold", meta.className)}>
          <meta.icon className="w-3.5 h-3.5" /> {spec ? meta.label : "기획서 미생성"}
        </span>
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
          <p className="text-muted-foreground font-medium flex items-center gap-1.5">
            원본 회의록 / 메모
            {rawLocked && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground/70">
                <Lock className="w-3 h-3" /> 기획서 생성 후에는 수정할 수 없습니다
              </span>
            )}
          </p>
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
      </div>

      <p className="text-sm text-muted-foreground font-semibold">기획서</p>
      <div className="border border-border rounded-xl overflow-hidden bg-black/10 dark:bg-black/30 p-4 flex flex-col items-center gap-3">
        {parsedContent ? (
          <div className="w-full max-w-[840px] max-h-[1190px] overflow-y-auto bg-white dark:bg-white">
            <div id="print-area">
              <ProposalTemplate
                doc={parsedContent}
                title={note.title} dateLabel={dateLabel}
                editable={editMode} onChange={setEditDraft}
                periodEditable={periodEditable} onPeriodChange={handlePeriodChange}
              />
            </div>
          </div>
        ) : (
          <div className="w-full max-w-[840px] bg-white dark:bg-white p-10 text-center text-muted-foreground text-sm">
            {!canGenerate ? "다른 사용자가 시작한 회의록입니다. 작성자 본인만 생성할 수 있습니다." : "AI가 아직 기획서를 생성하지 않았습니다."}
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

        {!spec && canGenerate && (
          <button
            onClick={onGenerateSpec}
            disabled={busy === busyKey("generate")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {busy === busyKey("generate") ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
            기획서 생성
          </button>
        )}

        {spec && !isPM && canGenerate && status === "DRAFT" && (
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

        {spec && isPM && status === "PENDING_REVIEW" && (
          <>
            <button
              onClick={() => onReject(spec)}
              disabled={busy === busyKey("reject")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-bold hover:bg-red-500/20 disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" /> 반려
            </button>
            <button
              onClick={() => onApprove(spec)}
              disabled={busy === busyKey("approve")}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 text-white text-sm font-bold hover:bg-emerald-600 disabled:opacity-50"
            >
              {busy === busyKey("approve") ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              승인
            </button>
          </>
        )}
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
            <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
              <meta.icon className="w-3 h-3" /> {spec ? meta.label : "기획서 미생성"}
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
            busy={busy}
            onCreate={() => onCreateReqDef(spec!)}
            onExtract={onExtractItems}
            onAddItem={onAddItem}
          />
        )}
      </div>

      {/* 업무배분 탭 — AI 로직(ai/assignee_mapping, ai/task_generation)은 있지만 이를 호출하는
          Django 엔드포인트가 아직 없어서(백엔드 전달 목록에 포함됨) 자리만 잡아둔다. */}
      <div className={cn(activeTab !== "taskAssignment" && "hidden")}>
        <div className="border border-dashed border-border rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <Briefcase className="w-8 h-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">업무배분 기능은 백엔드 API 준비 중입니다.</p>
        </div>
      </div>
    </div>
  );
}

function RequirementSection({
  spec, reqDef, isPM, busy, onCreate, onExtract, onAddItem,
}: {
  spec: SpecDto; reqDef: ReqDefDto | null; isPM: boolean; busy: string | null;
  onCreate: () => void;
  onExtract: (specId: number, reqDefId: number) => void;
  onAddItem: (reqDefId: number, item: { req_code: string; req_name: string; description: string }) => void;
}) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const creating = busy === `${spec.id}-create-reqdef`;
  const extracting = reqDef && busy === `reqdef-${reqDef.id}-extract`;
  const addingItem = reqDef && busy === `reqdef-${reqDef.id}-additem`;

  if (!reqDef) {
    return (
      <div className="border-t border-border pt-5 mt-2">
        <h3 className="font-bold text-sm mb-2">요구사항 정의서</h3>
        {!isPM ? (
          <button
            onClick={onCreate}
            disabled={creating}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
            요구사항 정의서 생성
          </button>
        ) : (
          <p className="text-sm text-muted-foreground">아직 요구사항 정의서가 생성되지 않았습니다.</p>
        )}
      </div>
    );
  }

  return (
    <div className="border-t border-border pt-5 mt-2 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-sm">{reqDef.title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{reqDef.version} · 항목 {reqDef.items.length}건</p>
        </div>
        {!isPM && (
          <button
            onClick={() => onExtract(spec.id, reqDef.id)}
            disabled={!!extracting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 disabled:opacity-50"
            title="기획서를 분석하여 요구사항 항목을 자동으로 추출합니다."
          >
            {extracting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5" />}
            AI 자동 추출
          </button>
        )}
      </div>

      {reqDef.items.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center">아직 요구사항 항목이 없습니다.</p>
      ) : (
        <div className="border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
              <tr>
                <th className="px-4 py-2.5 font-bold w-14">순번</th>
                <th className="px-4 py-2.5 font-bold w-24">분류</th>
                <th className="px-4 py-2.5 font-bold w-24">코드</th>
                <th className="px-4 py-2.5 font-bold">요구사항명</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {reqDef.items.map((item, index) => (
                <tr key={item.id}>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground align-top">{index + 1}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground align-top">
                    {/* req_code 접두사(FR/NFR)로 기능·비기능을 구분한다 — category 필드는
                        도메인 세부분류(재고 관리, 보안성 등)라 기능/비기능 여부와는 다르다. */}
                    {item.req_code?.startsWith("NFR") ? "비기능" : item.req_code?.startsWith("FR") ? "기능" : "-"}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground align-top">{item.req_code}</td>
                  <td className="px-4 py-2.5 align-top">
                    <p className="font-semibold">{item.req_name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                    <p className="text-xs text-muted-foreground/70 mt-0.5">
                      {item.category || "-"}{item.difficulty && ` · 난이도 ${item.difficulty}`}
                    </p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!isPM && (
        showAddForm ? (
          <div className="border border-border rounded-xl p-4 space-y-2">
            <div className="grid grid-cols-[120px_1fr] gap-2">
              <input
                value={newCode}
                onChange={e => setNewCode(e.target.value)}
                placeholder="REQ-03"
                className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="요구사항명"
                className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
            <textarea
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              placeholder="상세 내용"
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm resize-none h-20 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAddForm(false)} className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg">취소</button>
              <button
                onClick={() => {
                  if (!newCode.trim() || !newName.trim()) return;
                  onAddItem(reqDef.id, { req_code: newCode.trim(), req_name: newName.trim(), description: newDesc.trim() });
                  setNewCode(""); setNewName(""); setNewDesc(""); setShowAddForm(false);
                }}
                disabled={!newCode.trim() || !newName.trim() || !!addingItem}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
              >
                {addingItem ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                추가
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
          >
            <Plus className="w-3.5 h-3.5" /> 항목 직접 추가
          </button>
        )
      )}
    </div>
  );
}