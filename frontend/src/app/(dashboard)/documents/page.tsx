"use client";

import { useEffect, useState, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import {
  FileText, Plus, Bot, Loader2, Send, CheckCircle2, XCircle,
  AlertCircle, Clock, RotateCcw, MessageSquare, X, FolderKanban,
  Download, Printer, Trash2, Save, Pencil, Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { NewDocumentModal } from "@/components/projects/NewDocumentModal";
import { ProposalTemplate } from "@/components/documents/ProposalTemplate";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import type { ProposalDoc } from "@/lib/documentTemplates";
import { Toast } from "@/components/ui/Toast";

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

// 백엔드가 실제로 지원하는 상태는 4가지뿐 — PROPOSAL_ 접두사는 CommonCode.code_id가 테이블
// 전체에서 전역 유일해(REQSPEC_STATUS와 겹치지 않도록) 붙인 것이라 화면 표시에서는 벗겨서 쓴다.
type BareStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";
const bareStatus = (spec: SpecDto | null): BareStatus =>
  ((spec?.status_info?.code_id ?? "").replace(/^PROPOSAL_/, "") || "DRAFT") as BareStatus;

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
    // 회의록 원문에 기간이 명시돼 있으면 AI 분석 시점에 자동으로 채워지고(백엔드
    // MeetingNoteAnalyzeView), 없으면 null — 화면(ProposalTemplate)에서 직접 입력할 수 있다.
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

// 검토요청 중이거나 이미 승인된 기획서가 있는 회의록은 삭제하면 안 된다.
const isNoteDeletable = (note: NoteDto) => {
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
  const [loading, setLoading] = useState(true);
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);
  const [newDocModalOpen, setNewDocModalOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<{ specId: number } | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);

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
        const noteList = await apiFetch<NoteDto[]>(`/api/meetings/notes/?project=${current.id}`);
        setNotes(noteList);
      } else {
        setNotes([]);
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
      alert(err.message || "기획서 생성에 실패했습니다.");
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
      alert(err.message || "저장에 실패했습니다.");
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
      alert(err.message || "저장에 실패했습니다.");
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
      alert(err.message || "저장에 실패했습니다.");
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
      alert(err.message || "검토 요청에 실패했습니다.");
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
      alert(err.message || "승인에 실패했습니다.");
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
      alert(err.message || "반려에 실패했습니다.");
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
      alert(err.message || "삭제에 실패했습니다.");
    } finally {
      setDeleting(false);
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
              if (createdNoteId) setSelectedNoteId(createdNoteId);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="w-full space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold">문서생성</h1>
          <p className="text-sm text-muted-foreground mt-1">
            회의록을 기반으로 기획서를 작성하고 검토·승인합니다.
            <span className="ml-2 text-xs text-muted-foreground/70">(요구사항정의서·업무배분 단계는 백엔드 API 준비 중)</span>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-6 items-start">
        {/* Document list */}
        <div className="glass rounded-2xl border border-border p-4 space-y-3">
          {/* PM은 회의록/기획서/요구사항정의서를 생성하지 않고 검토(승인/반려)만 한다 —
              문서 생성은 일반유저 역할이므로 PM에게는 생성 버튼 자체를 숨긴다. */}
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
                    <button onClick={() => setSelectedNoteId(note.id)} className="flex-1 min-w-0 text-left">
                      <p className="font-semibold text-sm truncate mb-1.5">{note.title}</p>
                      <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", spec ? meta.className : "bg-black/5 dark:bg-white/5 text-muted-foreground")}>
                        <Icon className="w-3 h-3" /> {spec ? meta.label : "기획서 미생성"}
                      </span>
                      <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5">
                        <span>{new Date(note.meeting_date ?? note.updated_at).toLocaleDateString("ko-KR")}</span>
                        <span className="text-muted-foreground/60">·</span>
                        <span className="truncate">작성자 {note.created_by_name || "알 수 없음"}</span>
                      </p>
                    </button>
                    {isNoteDeletable(note) ? (
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
            if (createdNoteId) setSelectedNoteId(createdNoteId);
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
    </div>
  );
}

function NoteDetail({
  note, isPM, currentUserId, busy,
  onGenerateSpec, onSaveNoteContent, onSaveSpec, onSavePeriod, onSubmitReview, onApprove, onReject,
}: {
  note: NoteDto; isPM: boolean; currentUserId: string | undefined; busy: string | null;
  onGenerateSpec: () => void;
  onSaveNoteContent: (content: string) => void;
  onSaveSpec: (spec: SpecDto, doc: ProposalDoc) => void;
  onSavePeriod: (spec: SpecDto, period: { start: string; end: string }) => void;
  onSubmitReview: (spec: SpecDto) => void;
  onApprove: (spec: SpecDto) => void;
  onReject: (spec: SpecDto) => void;
}) {
  const spec = note.spec_documents[0] ?? null;
  const status = bareStatus(spec);
  const meta = STATUS_META[status];
  const canGenerate = String(note.created_by) === currentUserId;
  const dateLabel = new Date(note.updated_at).toLocaleDateString("ko-KR");

  const busyKey = (action: string) => `${note.id}-${action}`;

  const [rawDraft, setRawDraft] = useState(note.content ?? "");
  useEffect(() => { setRawDraft(note.content ?? ""); }, [note.id, note.content]);
  const rawDirty = rawDraft !== (note.content ?? "");
  const rawSaving = busy === busyKey("save-raw");
  // 기획서가 한 번이라도 생성되면 그 순간의 회의록 내용을 근거로 AI가 만든 것이므로, 이후에
  // 원본을 고치면 기획서와 내용이 어긋난다 — 그래서 검토중/승인됨뿐 아니라 기획서가 존재하는
  // 한(초안/반려 포함) 항상 잠근다(수정 화면 자체가 없도록 — 저장 버튼도 자동으로 숨겨짐).
  const rawLocked = !!spec;
  // 기획서 자체(직접수정 모드/기간)의 잠금은 검토중/승인됨일 때만 — 이건 원본 회의록과 별개다.
  const specLocked = status === "PENDING_REVIEW" || status === "APPROVED";

  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<ProposalDoc | null>(null);
  useEffect(() => { setEditMode(false); setEditDraft(null); }, [note.id]);
  const editSaving = busy === busyKey("save-spec");

  // 기간은 "직접 수정" 모드를 켜지 않아도 항상 바로 입력할 수 있다 — 검토중/승인됨일 때만
  // 잠근다(원본 회의록 잠금과 같은 기준). 값이 바뀌는 즉시 저장한다(날짜 선택은 텍스트
  // 입력과 달리 클릭 한 번짜리 이산적인 동작이라 별도 저장 버튼 없이 바로 반영해도 된다).
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
          {!rawLocked && rawDirty && (
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
          onChange={e => !rawLocked && setRawDraft(e.target.value)}
          readOnly={rawLocked}
          placeholder="내용이 없습니다."
          className={cn(
            "w-full h-48 bg-black/5 dark:bg-white/5 border border-border rounded-xl p-4 whitespace-pre-wrap overflow-y-auto text-muted-foreground resize-none focus:outline-none transition-all",
            rawLocked ? "cursor-default" : "focus:ring-2 focus:ring-primary/40"
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

        {spec && (status === "REJECTED" || status === "DRAFT") && !editMode && (
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
  );
}
