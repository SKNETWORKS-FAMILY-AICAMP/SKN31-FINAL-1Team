"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  History as HistoryIcon, FileText, ListTodo, Loader2, CheckCircle2, XCircle,
  Clock, AlertCircle, FolderKanban, Bot, ChevronLeft, ChevronRight, X,
  User as UserIcon, CalendarIcon, ExternalLink, Printer, Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { parseProposalDoc, parseReqSpecDoc } from "@/lib/documentTemplates";
import { ProposalTemplate } from "@/components/documents/ProposalTemplate";
import { ReqSpecTemplate } from "@/components/documents/ReqSpecTemplate";
import { AgentBadge, type AgentKind } from "@/components/ui/AgentBadge";
import { exportProposalPptx } from "@/lib/exportProposalPptx";
import { exportReqSpecPptx } from "@/lib/exportReqSpecPptx";
import { exportReqSpecExcel } from "@/lib/exportReqSpecExcel";

const STATUS_META: Record<string, { label: string; className: string; icon: any }> = {
  DRAFT: { label: "초안", className: "bg-muted text-muted-foreground", icon: FileText },
  PENDING_REVIEW: { label: "검토 요청중", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  APPROVED: { label: "승인됨", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
  REJECTED: { label: "반려됨", className: "bg-red-500/10 text-red-500", icon: XCircle },
  BACKLOG: { label: "대기", className: "bg-muted text-muted-foreground", icon: Clock },
  PENDING_APPROVAL: { label: "배분승인대기", className: "bg-orange-500/10 text-orange-500", icon: Clock },
  IN_PROGRESS: { label: "진행 중", className: "bg-primary/10 text-primary", icon: FolderKanban },
  DONE: { label: "완료", className: "bg-emerald-500/10 text-emerald-500", icon: CheckCircle2 },
};

type ActivityItem = {
  // "agent-*" kinds는 별도 이벤트 로그 테이블이 없어, 현재 문서/업무 상태 스냅샷에서
  // "AI 에이전트가 생성/실행한 흔적"(생성된 콘텐츠·sourceDocumentId 존재 여부)을 역추적해 재구성한다.
  kind: "document-proposal" | "document-reqspec" | "task" | "agent-proposal" | "agent-reqspec" | "agent-task" | "agent-recommend";
  id: string;
  title: string;
  subtitle: string;
  status: string;
  rejectReason: string | null;
  updatedAt: string;
  // 클릭했을 때 상세보기를 열기 위한 원본 엔티티 참조 — document 계열은 docId+docType,
  // task 계열(agent-task 포함)은 taskId로 project.documents/project.tasks에서 원본을 다시 찾는다.
  docId?: string;
  docType?: "proposal" | "reqSpec";
  taskId?: string;
  // agent-recommend 전용 — AssigneeRecommendation.id로 project.assigneeRecommendations에서
  // 그 시점 후보 목록(candidateData)을 다시 찾는다. 이건 역추적이 아니라 실제 저장된 이력이다.
  recommendationId?: string;
};

const AGENT_KINDS: ActivityItem["kind"][] = ["agent-proposal", "agent-reqspec", "agent-task", "agent-recommend"];

// 리스트에서 로봇 아이콘만 봐서는 에이전트 종류 구분이 안 된다는 피드백 —
// 종류별로 아이콘 색을 다르게 칠하고(빠른 스캔용), 뱃지 텍스트도 함께 보여준다(확정용).
// AgentBadge.tsx의 색 배정과 반드시 맞춰야 한다. agent-recommend는 "업무 배분" 에이전트가
// 담당자를 추천하는 단계라 taskAssign과 같은 색으로 묶는다(업무 자동생성과는 다른 단계지만
// 같은 에이전트 범주).
const agentOfKind = (kind: ActivityItem["kind"]): AgentKind | null =>
  kind === "agent-proposal" ? "proposal" : kind === "agent-reqspec" ? "reqSpec" : (kind === "agent-task" || kind === "agent-recommend") ? "taskAssign" : null;

const AGENT_ICON_CLASS: Record<AgentKind, string> = {
  proposal: "bg-blue-500/10 text-blue-500",
  reqSpec: "bg-violet-500/10 text-violet-500",
  taskAssign: "bg-teal-500/10 text-teal-500",
};

export default function HistoryPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [project, setProject] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "document" | "task" | "agent">("all");
  const [page, setPage] = useState(1);
  const [selectedItem, setSelectedItem] = useState<ActivityItem | null>(null);
  const PAGE_SIZE = 10;

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // 예전엔 목록 조회 → 첫 프로젝트 id로 상세 조회 2단계였다 — 원격 DB 왕복이 하나 늘 때마다
        // 체감 지연이 커서(/api/projects/current 참고) 단일 요청으로 합쳤다.
        const res = await fetch("/api/projects/current");
        const detail = await res.json();
        if (detail.success) setProject(detail.data);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const activity: ActivityItem[] = useMemo(() => {
    if (!project) return [];
    const items: ActivityItem[] = [];

    for (const doc of project.documents ?? []) {
      const proposal = parseProposalDoc(doc.proposalContent);
      if (proposal || doc.proposalStatus !== "DRAFT") {
        items.push({
          kind: "document-proposal",
          id: `${doc.id}-proposal`,
          title: doc.title,
          subtitle: "기획서",
          status: doc.proposalStatus,
          rejectReason: doc.proposalRejectReason,
          updatedAt: doc.updatedAt,
          docId: doc.id,
          docType: "proposal",
        });
      }
      if (doc.reqSpecContent) {
        items.push({
          kind: "document-reqspec",
          id: `${doc.id}-reqspec`,
          title: doc.title,
          subtitle: "요구사항정의서",
          status: doc.reqSpecStatus,
          rejectReason: doc.reqSpecRejectReason,
          updatedAt: doc.updatedAt,
          docId: doc.id,
          docType: "reqSpec",
        });
      }
    }

    for (const task of project.tasks ?? []) {
      items.push({
        kind: "task",
        id: task.id,
        title: task.title,
        subtitle: task.assignee ? `담당: ${task.assignee.name}` : "미배정",
        status: task.status,
        rejectReason: task.rejectReason,
        updatedAt: task.updatedAt,
        taskId: task.id,
      });

      // 에이전트3(요구사항정의서 기반 업무 자동배분)이 만든 업무는 sourceDocumentId를 가진다 — 이를 근거로 역추적
      if (task.sourceDocumentId) {
        items.push({
          kind: "agent-task",
          id: `${task.id}-agent`,
          title: task.title,
          subtitle: "요구사항정의서 기반 업무 자동 생성",
          status: task.status,
          rejectReason: null,
          updatedAt: task.createdAt ?? task.updatedAt,
          taskId: task.id,
        });
      }
    }

    // 에이전트1(회의록/기획서 생성), 에이전트2(요구사항정의서 생성)가 실행된 흔적
    for (const doc of project.documents ?? []) {
      if (doc.proposalContent) {
        items.push({
          kind: "agent-proposal",
          id: `${doc.id}-agent-proposal`,
          title: doc.title,
          subtitle: "회의록 → 기획서 AI 초안 생성",
          status: doc.proposalStatus,
          rejectReason: null,
          updatedAt: doc.updatedAt,
          docId: doc.id,
          docType: "proposal",
        });
      }
      if (doc.reqSpecContent) {
        items.push({
          kind: "agent-reqspec",
          id: `${doc.id}-agent-reqspec`,
          title: doc.title,
          subtitle: "기획서 → 요구사항정의서 AI 생성",
          status: doc.reqSpecStatus,
          rejectReason: null,
          updatedAt: doc.updatedAt,
          docId: doc.id,
          docType: "reqSpec",
        });
      }
    }

    // 에이전트(담당자 추천)가 실행된 이력 — 위 항목들과 달리 상태 스냅샷에서 역추적한 게 아니라
    // AssigneeRecommendation 테이블에 그 시점 후보 전체가 실제로 저장돼 있다(확정 여부 무관).
    for (const rec of project.assigneeRecommendations ?? []) {
      const relatedTask = (project.tasks ?? []).find((t: any) => t.id === rec.taskId);
      items.push({
        kind: "agent-recommend",
        id: `rec-${rec.id}`,
        title: relatedTask?.title ?? "(삭제된 업무)",
        subtitle: "담당자 추천 실행",
        status: relatedTask?.status ?? "BACKLOG",
        rejectReason: null,
        updatedAt: rec.createdAt,
        taskId: rec.taskId,
        recommendationId: rec.id,
      });
    }

    return items
      .filter(i => {
        if (filter === "all") return true;
        if (filter === "agent") return AGENT_KINDS.includes(i.kind);
        if (filter === "document") return i.kind === "document-proposal" || i.kind === "document-reqspec";
        return i.kind === "task";
      })
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  }, [project, filter]);

  // 필터가 바뀌면 목록이 통째로 달라지므로 페이지를 1로 되돌린다
  useEffect(() => { setPage(1); }, [filter]);

  const totalPages = Math.max(1, Math.ceil(activity.length / PAGE_SIZE));
  // 필터가 아닌 다른 이유로 목록이 줄어들 수도 있으므로, 지금 페이지가 범위를 넘으면 마지막 페이지로 당긴다
  useEffect(() => { setPage(p => Math.min(p, totalPages)); }, [totalPages]);
  const pagedActivity = activity.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const relativeTime = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "방금 전";
    if (mins < 60) return `${mins}분 전`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}시간 전`;
    return `${Math.floor(hrs / 24)}일 전`;
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

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">
          회의록 등록부터 기획서·요구사항정의서 검토, 업무 진행까지 전체 파이프라인 이력입니다.
        </p>
      </div>

      <div className="flex items-center gap-1 p-1 bg-black/5 dark:bg-white/5 rounded-xl w-fit">
        {([
          { key: "all", label: "전체" },
          { key: "document", label: "문서" },
          { key: "task", label: "업무" },
          { key: "agent", label: "에이전트" },
        ] as { key: typeof filter; label: string }[]).map(tab => (
          <button
            key={tab.key}
            onClick={() => setFilter(tab.key)}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-bold transition-all",
              filter === tab.key ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activity.length === 0 ? (
        <div className="glass rounded-2xl border border-border p-16 text-center">
          <HistoryIcon className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
          <p className="text-muted-foreground text-sm">아직 이력이 없습니다.</p>
        </div>
      ) : (
        <div className="glass rounded-2xl border border-border divide-y divide-border overflow-hidden">
          {pagedActivity.map(item => {
            const meta = STATUS_META[item.status] ?? STATUS_META.DRAFT;
            const Icon = meta.icon;
            const isAgent = AGENT_KINDS.includes(item.kind);
            const agentKind = agentOfKind(item.kind);
            const KindIcon = isAgent ? Bot : item.kind === "task" ? ListTodo : FileText;
            return (
              <button
                key={item.id}
                onClick={() => setSelectedItem(item)}
                className="w-full flex items-start gap-4 p-4 hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left"
              >
                <div className={cn(
                  "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
                  agentKind ? AGENT_ICON_CLASS[agentKind] : "bg-black/5 dark:bg-white/5 text-muted-foreground"
                )}>
                  <KindIcon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm truncate">{item.title}</span>
                    <span className="text-[11px] text-muted-foreground shrink-0">· {item.subtitle}</span>
                    {agentKind && <AgentBadge agent={agentKind} />}
                  </div>
                  {item.rejectReason && item.status === "REJECTED" && (
                    <p className="text-[11px] text-red-400 mt-1 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3 shrink-0" /> {item.rejectReason}
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
                    <Icon className="w-3 h-3" /> {meta.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground">{relativeTime(item.updatedAt)}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1.5">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(n => (
            <button
              key={n}
              onClick={() => setPage(n)}
              className={cn(
                "w-8 h-8 rounded-lg text-sm font-bold transition-colors",
                n === page ? "bg-primary text-primary-foreground" : "bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-muted-foreground"
              )}
            >
              {n}
            </button>
          ))}
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {selectedItem && (
        <HistoryDetailModal
          item={selectedItem}
          project={project}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
}

// 히스토리 목록에서 항목을 클릭했을 때 뜨는 상세보기 — 히스토리 자체는 과거 시점 스냅샷을 따로
// 저장하지 않으므로(이벤트 로그 테이블이 없음), 그 항목이 가리키는 문서/업무의 "현재" 전체 내용을
// 읽기 전용으로 보여준다. 실제로 고치려면 문서생성/업무관리로 이동해야 한다("~에서 열기" 링크).
function HistoryDetailModal({ item, project, onClose }: { item: ActivityItem; project: any; onClose: () => void }) {
  const isAgent = AGENT_KINDS.includes(item.kind);

  // 문서 계열: 기획서/요구사항정의서 (+ 그걸 만든 에이전트 이벤트)
  if (item.docId && item.docType) {
    const doc = (project?.documents ?? []).find((d: any) => d.id === item.docId);
    if (!doc) return null;
    const status = item.docType === "proposal" ? doc.proposalStatus : doc.reqSpecStatus;
    const rejectReason = item.docType === "proposal" ? doc.proposalRejectReason : doc.reqSpecRejectReason;
    const content = item.docType === "proposal" ? doc.proposalContent : doc.reqSpecContent;
    const meta = STATUS_META[status] ?? STATUS_META.DRAFT;
    const parsedProposal = item.docType === "proposal" ? parseProposalDoc(content) : null;
    const parsedReqSpec = item.docType === "reqSpec" ? parseReqSpecDoc(content) : null;
    const dateLabel = new Date(doc.updatedAt).toLocaleDateString("ko-KR");

    const handlePrint = () => window.print();
    const handlePptx = async () => {
      if (item.docType === "proposal" && parsedProposal) await exportProposalPptx(parsedProposal, doc.title);
      else if (item.docType === "reqSpec" && parsedReqSpec) await exportReqSpecPptx(parsedReqSpec, doc.title);
    };
    const handleExcel = async () => {
      if (parsedReqSpec) await exportReqSpecExcel(parsedReqSpec, doc.title);
    };
    const hasContent = !!(parsedProposal || parsedReqSpec);

    return (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-background border border-border rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-lg font-bold">{doc.title}</h3>
                <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
                  <meta.icon className="w-3 h-3" /> {meta.label}
                </span>
                {isAgent && <AgentBadge agent={item.docType === "proposal" ? "proposal" : "reqSpec"} />}
              </div>
              <p className="text-xs text-muted-foreground">
                {item.docType === "proposal" ? "기획서" : "요구사항정의서"}{isAgent && " · AI 에이전트가 생성"}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Link
                href={`/documents?docId=${doc.id}&tab=${item.docType}`}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-colors"
              >
                문서생성에서 열기 <ExternalLink className="w-3.5 h-3.5" />
              </Link>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
          </div>

          {rejectReason && status === "REJECTED" && (
            <div className="mx-5 mt-4 flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 shrink-0">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div><span className="font-semibold">반려 사유:</span> {rejectReason}</div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-5">
            <div id="print-area" className="border border-border rounded-xl overflow-hidden bg-black/5 dark:bg-black/20">
              {parsedProposal ? (
                <ProposalTemplate doc={parsedProposal} title={doc.title} dateLabel={dateLabel} />
              ) : parsedReqSpec ? (
                <ReqSpecTemplate doc={parsedReqSpec} title={doc.title} dateLabel={dateLabel} />
              ) : (
                <div className="p-10 text-center text-muted-foreground text-sm">아직 생성된 내용이 없습니다.</div>
              )}
            </div>
          </div>

          {hasContent && (
            <div className="flex items-center gap-2 p-5 pt-0 shrink-0">
              <button onClick={handlePrint} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
                <Printer className="w-3.5 h-3.5" /> PDF 다운로드
              </button>
              <button onClick={handlePptx} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
                <Download className="w-3.5 h-3.5" /> PPTX 다운로드
              </button>
              {parsedReqSpec && (
                <button onClick={handleExcel} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition-colors">
                  <Download className="w-3.5 h-3.5" /> EXCEL 다운로드
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // 담당자 추천 이력 — 다른 agent-* 항목과 달리 상태 스냅샷 역추적이 아니라 그 시점 AI가
  // 제시한 후보 전체(확정 여부 무관)가 AssigneeRecommendation에 실제로 저장돼 있다.
  if (item.kind === "agent-recommend") {
    const rec = (project?.assigneeRecommendations ?? []).find((r: any) => r.id === item.recommendationId);
    let candidates: Array<{ userId?: string; name?: string; fitScore?: number; techFit?: string; workloadFit?: string; experienceFit?: string }> = [];
    try { candidates = rec?.candidateData ? JSON.parse(rec.candidateData) : []; } catch {}
    const relatedTask = (project?.tasks ?? []).find((t: any) => t.id === item.taskId);

    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
        <div className="bg-background border border-border rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-lg font-bold">{item.title}</h3>
                <AgentBadge agent="taskAssign" />
              </div>
              <p className="text-xs text-muted-foreground">
                담당자 추천 실행{rec ? ` · ${new Date(rec.createdAt).toLocaleString("ko-KR")}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {relatedTask && (
                <Link href="/tasks" className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-colors">
                  업무관리에서 열기 <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              )}
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-3 text-sm">
            <p className="text-xs text-muted-foreground">
              이 시점에 AI가 제시한 후보 {candidates.length}명입니다 — 실제로 배정에 반영됐는지와 무관하게 그대로 기록된 이력입니다.
            </p>
            {candidates.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground text-xs">저장된 후보 정보가 없습니다.</div>
            ) : (
              candidates
                .slice()
                .sort((a, b) => (b.fitScore ?? 0) - (a.fitScore ?? 0))
                .map((c, i) => (
                  <div key={i} className="border border-border rounded-xl p-3 space-y-1.5">
                    <p className="text-xs font-semibold flex items-center gap-1.5">
                      <UserIcon className="w-3.5 h-3.5 text-primary" /> {c.name ?? "이름 없음"} (적합도 {c.fitScore}점)
                      {relatedTask?.assigneeId && relatedTask.assigneeId === c.userId && (
                        <span className="ml-auto px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-500">현재 담당자</span>
                      )}
                    </p>
                    <ul className="text-xs text-muted-foreground space-y-1 pl-4 list-disc">
                      <li>기술 적합도: {c.techFit ?? "-"}</li>
                      <li>업무 여유도: {c.workloadFit ?? "-"}</li>
                      <li>유사 경험: {c.experienceFit ?? "-"}</li>
                    </ul>
                  </div>
                ))
            )}
          </div>
        </div>
      </div>
    );
  }

  // 업무 계열: 업무 배정/진행 (+ 요구사항정의서 기반 자동생성 에이전트 이벤트)
  if (item.taskId) {
    const task = (project?.tasks ?? []).find((t: any) => t.id === item.taskId);
    if (!task) return null;
    const meta = STATUS_META[task.status] ?? STATUS_META.BACKLOG;
    let reason: any = null;
    try { reason = task.assignmentReason ? JSON.parse(task.assignmentReason) : null; } catch {}

    return (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-background border border-border rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-lg font-bold">{task.title}</h3>
                <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold", meta.className)}>
                  <meta.icon className="w-3 h-3" /> {meta.label}
                </span>
                {isAgent && <AgentBadge agent="taskAssign" />}
              </div>
              <p className="text-xs text-muted-foreground">업무{isAgent && " · AI 에이전트가 배정"}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Link href="/tasks" className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-colors">
                업무관리에서 열기 <ExternalLink className="w-3.5 h-3.5" />
              </Link>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-4 text-sm">
            {task.description && <p className="text-muted-foreground whitespace-pre-wrap">{task.description}</p>}

            {task.rejectReason && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div><span className="font-semibold">반려 사유:</span> {task.rejectReason}</div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1"><UserIcon className="w-3 h-3" /> 담당자</p>
                <p className="font-semibold">{task.assignee?.name ?? "미배정"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-1">예상 소요시간</p>
                <p className="font-semibold">{task.estimatedHours ?? "-"}h</p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1"><CalendarIcon className="w-3 h-3" /> 일정</p>
                <p className="font-semibold">
                  {task.wbsStart && task.wbsEnd ? `${new Date(task.wbsStart).toLocaleDateString("ko-KR")} ~ ${new Date(task.wbsEnd).toLocaleDateString("ko-KR")}` : "미정"}
                </p>
              </div>
            </div>

            {reason && (
              <div className="border border-border rounded-xl p-3 space-y-1.5">
                <p className="text-xs font-semibold flex items-center gap-1.5">
                  <Bot className="w-3.5 h-3.5 text-primary" /> AI 배정 근거 (적합도 {reason.fitScore}점)
                </p>
                <ul className="text-xs text-muted-foreground space-y-1 pl-4 list-disc">
                  <li>기술 적합도: {reason.techFit ?? "-"}</li>
                  <li>업무 여유도: {reason.workloadFit ?? "-"}</li>
                  <li>유사 경험: {reason.experienceFit ?? "-"}</li>
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
