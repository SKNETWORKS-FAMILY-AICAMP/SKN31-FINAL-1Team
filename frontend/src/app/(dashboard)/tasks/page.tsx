"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { FolderKanban, Search, LayoutGrid, MoreVertical, Loader2, ArrowRight, ChevronLeft, ChevronRight, ClipboardList, GitBranch, GitPullRequest, GitMerge, X, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { KanbanBoard } from "@/components/layout/KanbanBoard";
import { TaskDetailModal } from "@/components/projects/TaskDetailModal";
import { isTaskOverdue } from "@/lib/taskOverdue";

type Task = {
  id: string;
  title: string;
  description: string | null;
  status: string;
  estimatedHours: number | null;
  gitStatus: string;
  wbsStart: string | null;
  wbsEnd: string | null;
  progress: number;
  project: { id: string; name: string };
  assigneeId: string | null;
  assignee: { id: string; name: string } | null;
  rejectReason?: string | null;
  assignmentReason?: string | null;
};

type Member = { id: string; name: string; email: string; role: string };

const STATUSES = [
  { id: "BACKLOG", label: "대기", color: "text-muted-foreground", bg: "bg-muted" },
  { id: "PENDING_APPROVAL", label: "배분승인대기", color: "text-orange-500", bg: "bg-orange-500/10" },
  { id: "IN_PROGRESS", label: "진행 중", color: "text-amber-500", bg: "bg-amber-500/10" },
  { id: "DONE", label: "완료", color: "text-emerald-500", bg: "bg-emerald-500/10" },
];

// FR-07-003: 업무 항목별 Git 상태 배지 (실제 Git 연동 전까지는 수동 표시 — FR-08에서 자동화 예정)
const GIT_STATUSES: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  NONE: { label: "미연동", color: "text-muted-foreground", bg: "bg-muted", icon: GitBranch },
  PENDING: { label: "대기", color: "text-gray-500", bg: "bg-gray-500/10", icon: GitBranch },
  IN_REVIEW: { label: "PR리뷰중", color: "text-orange-500", bg: "bg-orange-500/10", icon: GitPullRequest },
  MERGED: { label: "완료", color: "text-emerald-500", bg: "bg-emerald-500/10", icon: GitMerge },
};

export default function TasksPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const searchParams = useSearchParams();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // 대시보드 "업무 상태 분포" 차트에서 ?status=IN_PROGRESS 같은 링크로 들어오면 그 상태로 미리 필터링한다.
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  useEffect(() => {
    const s = searchParams.get("status");
    if (s) setStatusFilter(s);
  }, [searchParams]);

  // 일반유저는 "내 업무"가 기본값 — 전체 업무 조회는 PM만 필요하다는 판단(FR-01-005 팀 전체 요약은 PM용)
  const [filterScope, setFilterScope] = useState<"ME" | "ALL">("ME");
  const [viewMode, setViewMode] = useState<"KANBAN" | "LIST" | "WBS">("LIST");
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 10;

  // 칸반 뷰(KanbanBoard 컴포넌트)는 담당자 배정에 프로젝트 멤버 목록이 필요하고,
  // 신규 업무 생성에는 프로젝트 id가 필요하다 — 이 앱은 단일 프로젝트 전제이므로
  // 다른 화면들과 같은 방식으로 가장 최근(첫 번째) 프로젝트를 기본값으로 쓴다.
  const [members, setMembers] = useState<Member[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  // 리스트/WBS 뷰 행을 눌러도 아무 반응이 없었다 — 칸반 카드와 동일하게 상세 모달을 연다.
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<Task | null>(null);

  useEffect(() => {
    fetchTasks();
    Promise.all([
      fetch("/api/projects").then(r => r.json()),
      fetch("/api/users").then(r => r.json()),
    ]).then(([projectsRes, usersRes]) => {
      const projects = Array.isArray(projectsRes) ? projectsRes : projectsRes.data || [];
      setCurrentProjectId(projects[0]?.id ?? null);
      // PM은 배정 대상이 아니고, 온보딩 전이라 이름이 비어있는 계정은 제외한다 (projects/[id] 페이지와 동일한 기준).
      if (usersRes.success) setMembers(usersRes.data.filter((u: Member) => u.role !== "PM" && u.name?.trim()));
    }).catch(error => console.error(error));
  }, []);

  // 로그인 정보가 로드된 뒤 역할에 맞는 기본 필터로 맞춘다 (PM은 전체 업무를 기본으로 봄)
  useEffect(() => {
    if (isPM) setFilterScope("ALL");
    else setFilterScope("ME");
  }, [isPM]);

  // silent=true는 이미 목록이 화면에 떠 있는 상태에서 데이터만 조용히 갱신할 때 쓴다(예: 상세
  // 모달 닫을 때) — 전체 화면 로딩 스피너로 목록을 통째로 갈아끼우면 리스트가 언마운트됐다
  // 다시 그려지면서 스크롤 위치가 맨 위로 튀는 문제가 있었다(사용자가 실제로 보고 발견함).
  const fetchTasks = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch("/api/tasks");
      const json = await res.json();
      if (json.success) setTasks(json.data);
    } catch (error) {
      console.error(error);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string) => {
    setProcessingId(taskId);
    try {
      const res = await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        setTasks(tasks.map(t => t.id === taskId ? { ...t, status: newStatus } : t));
      } else {
        alert("상태 변경에 실패했습니다.");
      }
    } catch {
      alert("네트워크 오류로 상태 변경에 실패했습니다.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleGitStatusChange = async (taskId: string, gitStatus: string) => {
    const prevStatus = tasks.find(t => t.id === taskId)?.gitStatus;
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, gitStatus } : t));
    try {
      const res = await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gitStatus }),
      });
      if (!res.ok) throw new Error("failed");
    } catch (e) {
      console.error(e);
      // 저장 실패 시 화면이 실제 상태와 어긋난 채로 남지 않도록 되돌린다
      if (prevStatus !== undefined) setTasks(prev => prev.map(t => t.id === taskId ? { ...t, gitStatus: prevStatus } : t));
      alert("Git 상태 변경에 실패했습니다.");
    }
  };

  const filteredTasks = useMemo(() => {
    let filtered = tasks;
    if (filterScope === "ME" && user) {
      filtered = filtered.filter(t => t.assignee?.id === user.id);
    }
    if (statusFilter) {
      filtered = filtered.filter(t => t.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(t => 
        t.title.toLowerCase().includes(q) || 
        t.project.name.toLowerCase().includes(q) ||
        (t.assignee?.name || "").toLowerCase().includes(q)
      );
    }
    return filtered;
  }, [tasks, filterScope, search, user, statusFilter]);

  // 탭·검색어가 바뀌면 목록이 통째로 달라지므로 페이지를 1로 되돌린다
  useEffect(() => { setPage(1); }, [filterScope, search, viewMode, statusFilter]);
  const totalPages = Math.max(1, Math.ceil(filteredTasks.length / PAGE_SIZE));
  // 위 리셋 대상이 아닌 다른 이유로 목록이 줄어들 수도 있으므로(다른 화면에서 상태 변경 후 재조회 등),
  // 지금 페이지가 범위를 넘으면 마지막 페이지로 당겨서 빈 화면이 뜨지 않게 한다
  useEffect(() => { setPage(p => Math.min(p, totalPages)); }, [totalPages]);
  const pagedTasks = filteredTasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">나의 업무를 관리하거나 전체 프로젝트의 진행 상태를 파악하세요.</p>
      </div>

      {/* Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-black/5 dark:bg-white/5 p-2 rounded-2xl border border-black/5 dark:border-white/10">
        <div className="flex items-center gap-2 p-1 bg-black/5 dark:bg-white/5 rounded-xl">
          <button
            onClick={() => setFilterScope("ME")}
            className={cn("px-5 py-2.5 rounded-lg text-sm font-bold transition-all", filterScope === "ME" ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            내 업무
          </button>
          {/* 전체 업무 조회는 PM만 필요 — 일반유저는 본인 업무만 관리하면 되므로 탭 자체를 숨긴다 */}
          {isPM && (
            <button
              onClick={() => setFilterScope("ALL")}
              className={cn("px-5 py-2.5 rounded-lg text-sm font-bold transition-all", filterScope === "ALL" ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              전체 업무
            </button>
          )}
        </div>

        <div className="flex items-center gap-4">
          <div className="relative group">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <input
              type="text"
              placeholder="업무명, 프로젝트, 담당자 검색..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2.5 bg-card border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:bg-background w-64 lg:w-80 transition-all shadow-sm"
            />
          </div>
          
          <div className="flex items-center gap-1 p-1 bg-black/5 dark:bg-white/5 rounded-xl">
            <button
              onClick={() => setViewMode("KANBAN")}
              className={cn("p-2.5 rounded-lg transition-all", viewMode === "KANBAN" ? "bg-white dark:bg-white/10 text-primary shadow-sm" : "text-muted-foreground hover:text-foreground")}
              title="칸반 뷰"
            >
              <FolderKanban className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode("LIST")}
              className={cn("p-2.5 rounded-lg transition-all", viewMode === "LIST" ? "bg-white dark:bg-white/10 text-primary shadow-sm" : "text-muted-foreground hover:text-foreground")}
              title="리스트 뷰"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            {/* 업무보드(WBS) 뷰 — FR-07: 전체 진행상황 요약 + Git 상태 배지가 포함된 표 형태 뷰 */}
            <button
              onClick={() => setViewMode("WBS")}
              className={cn("p-2.5 rounded-lg transition-all", viewMode === "WBS" ? "bg-white dark:bg-white/10 text-primary shadow-sm" : "text-muted-foreground hover:text-foreground")}
              title="업무보드(WBS) 뷰"
            >
              <ClipboardList className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* 대시보드 "업무 상태 분포"에서 상태를 지정해 들어왔을 때만 보이는 필터 표시 — 지금 뭘로
          좁혀서 보고 있는지 알려주고, 눌러서 지울 수 있게 한다. */}
      {statusFilter && (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-primary/10 text-primary">
            상태: {STATUSES.find(s => s.id === statusFilter)?.label ?? statusFilter}
            <button onClick={() => setStatusFilter(null)} className="hover:opacity-70 transition-opacity" aria-label="필터 해제">
              <X className="w-3 h-3" />
            </button>
          </span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-primary/50" />
        </div>
      ) : (
        <>
          {viewMode === "KANBAN" ? (
            currentProjectId ? (
              // FR-05: 업무분배 승인/반려는 KanbanBoard 컴포넌트로 통일한다 — 이전에는 이 화면이
              // 자체 칸반 마크업을 따로 갖고 있어서 PENDING_APPROVAL 카드에 승인/반려 버튼이 없었고,
              // 팀원이 매일 쓰는 이 화면에서는 승인함(/approvals)이나 프로젝트 상세 페이지로 가야만 승인할 수 있었다.
              <KanbanBoard projectId={currentProjectId} initialTasks={filteredTasks} members={members} />
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-center gap-3">
                <FolderKanban className="w-10 h-10 text-muted-foreground/30" />
                <p className="text-muted-foreground text-sm">아직 프로젝트가 없습니다.</p>
              </div>
            )
          ) : viewMode === "LIST" ? (
            <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-sm">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
                  <tr>
                    <th className="px-6 py-4 font-bold rounded-tl-2xl">업무명</th>
                    <th className="px-6 py-4 font-bold">상태</th>
                    <th className="px-6 py-4 font-bold">담당자</th>
                    <th className="px-6 py-4 font-bold">마감일</th>
                    <th className="px-6 py-4 font-bold text-center rounded-tr-2xl">진행률</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5">
                  {filteredTasks.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                        조건에 맞는 업무가 없습니다.
                      </td>
                    </tr>
                  ) : (
                    pagedTasks.map(task => {
                      const statusInfo = STATUSES.find(s => s.id === task.status) || STATUSES[0];
                      return (
                        <tr
                          key={task.id}
                          onClick={() => setSelectedTaskForDetail(task)}
                          className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors group relative cursor-pointer"
                        >
                          <td className="px-6 py-4">
                            <div className="font-bold mb-1">{task.title}</div>
                            {task.description && <div className="text-xs text-muted-foreground line-clamp-1 max-w-md">{task.description}</div>}
                          </td>
                          <td className="px-6 py-4" onClick={e => e.stopPropagation()}>
                            {task.status === "PENDING_APPROVAL" ? (
                              <span className={cn("inline-block text-xs font-bold px-2.5 py-1.5 rounded-lg", statusInfo.bg, statusInfo.color)}>
                                {statusInfo.label} · PM 승인 대기
                              </span>
                            ) : (
                              <select
                                value={task.status}
                                onChange={e => handleStatusChange(task.id, e.target.value)}
                                disabled={processingId === task.id}
                                className={cn(
                                  "text-xs font-bold px-2.5 py-1.5 rounded-lg border border-transparent hover:border-black/10 dark:hover:border-white/10 focus:outline-none transition-all cursor-pointer appearance-none",
                                  statusInfo.bg, statusInfo.color
                                )}
                              >
                                {STATUSES.filter(s => s.id !== "PENDING_APPROVAL").map(s => <option key={s.id} value={s.id} className="bg-background text-foreground">{s.label}</option>)}
                              </select>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            {task.assignee ? (
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-[10px] font-bold">
                                  {task.assignee.name.charAt(0)}
                                </div>
                                <span className="font-medium text-[13px]">{task.assignee.name}</span>
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-[13px]">미배정</span>
                            )}
                          </td>
                          <td className={cn("px-6 py-4 text-[13px]", isTaskOverdue(task) ? "text-red-500 font-semibold" : "text-muted-foreground")}>
                            <div className="flex items-center gap-1">
                              {isTaskOverdue(task) && <AlertTriangle className="w-3.5 h-3.5 shrink-0" />}
                              {task.wbsEnd ? new Date(task.wbsEnd).toLocaleDateString() : "-"}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-center gap-2">
                              <div className="w-16 h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
                                <div className="h-full bg-primary rounded-full" style={{ width: `${task.progress}%` }} />
                              </div>
                              <span className="text-xs font-semibold w-8 text-right">{task.progress}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
              <Pagination page={page} totalPages={totalPages} onChange={setPage} />
            </div>
          ) : (
            // 업무보드(WBS) 뷰 (FR-07-001~003): 전체 진행상황 요약 + Git 상태 배지가 포함된 통합 표
            <WbsBoardView tasks={filteredTasks} onGitStatusChange={handleGitStatusChange} onRowClick={setSelectedTaskForDetail} />
          )}
        </>
      )}

      {selectedTaskForDetail && (
        <TaskDetailModal
          task={selectedTaskForDetail}
          members={members}
          onClose={() => { setSelectedTaskForDetail(null); fetchTasks(true); }}
        />
      )}
    </div>
  );
}

/**
 * 업무보드(WBS) 뷰 — FR-07-003 "조회 상단 WBS: 전체 진행사항을 파악할 수 있는 차트 +
 * Git 상태 배지"를 담당한다. 상단에는 상태별 카운트/전체 진행률 요약 바를,
 * 아래에는 업무별 Git 상태(FR-08 연동 전까지는 수동 표시)를 포함한 표를 그린다.
 */
function WbsBoardView({ tasks, onGitStatusChange, onRowClick }: { tasks: Task[]; onGitStatusChange: (taskId: string, gitStatus: string) => void; onRowClick: (task: Task) => void }) {
  // 상태별 집계 — 진행률 요약 바에 사용 (페이지네이션과 무관하게 항상 전체 tasks 기준)
  const total = tasks.length;
  const counts = STATUSES.reduce((acc, s) => {
    acc[s.id] = tasks.filter(t => t.status === s.id).length;
    return acc;
  }, {} as Record<string, number>);
  const doneCount = counts["DONE"] ?? 0;
  const overallProgress = total > 0 ? Math.round((doneCount / total) * 100) : 0;

  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);
  useEffect(() => { setPage(1); }, [tasks]);
  const totalPages = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE));
  const pagedTasks = tasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      {/* 전체 진행상황 요약 (FR-07-003) */}
      <div className="bg-card rounded-2xl border border-border p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-muted-foreground">전체 진행률</h3>
          <span className="text-sm font-black text-primary">{overallProgress}% ({doneCount}/{total}건 완료)</span>
        </div>
        <div className="w-full h-2.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden mb-4">
          <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${overallProgress}%` }} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {STATUSES.map(s => (
            <div key={s.id} className={cn("rounded-xl p-3", s.bg)}>
              <p className={cn("text-xs font-bold", s.color)}>{s.label}</p>
              <p className="text-xl font-black mt-1">{counts[s.id] ?? 0}건</p>
            </div>
          ))}
        </div>
      </div>

      {/* 업무별 WBS 표 + Git 상태 배지 */}
      <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-sm">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-6 py-4 font-bold">업무명</th>
              <th className="px-6 py-4 font-bold">담당자</th>
              <th className="px-6 py-4 font-bold">상태</th>
              <th className="px-6 py-4 font-bold text-center">진행률</th>
              <th className="px-6 py-4 font-bold">Git 상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 dark:divide-white/5">
            {tasks.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">조건에 맞는 업무가 없습니다.</td></tr>
            ) : (
              pagedTasks.map(task => {
                const statusInfo = STATUSES.find(s => s.id === task.status) || STATUSES[0];
                const gitInfo = GIT_STATUSES[task.gitStatus] ?? GIT_STATUSES.NONE;
                const GitIcon = gitInfo.icon;
                return (
                  <tr
                    key={task.id}
                    onClick={() => onRowClick(task)}
                    className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold">{task.title}</span>
                        {isTaskOverdue(task) && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-500 shrink-0">
                            <AlertTriangle className="w-3 h-3" /> 지연
                          </span>
                        )}
                      </div>
                      {task.estimatedHours != null && (
                        <div className="text-[11px] text-muted-foreground mt-0.5">예상 소요 {task.estimatedHours}시간</div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-[13px]">{task.assignee ? task.assignee.name : <span className="text-muted-foreground">미배정</span>}</td>
                    <td className="px-6 py-4">
                      <span className={cn("inline-block text-xs font-bold px-2.5 py-1.5 rounded-lg", statusInfo.bg, statusInfo.color)}>
                        {statusInfo.label}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-16 h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full" style={{ width: `${task.progress}%` }} />
                        </div>
                        <span className="text-xs font-semibold w-8 text-right">{task.progress}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4" onClick={e => e.stopPropagation()}>
                      {/* FR-08 Git 연동 전까지는 팀원이 직접 상태를 표시 */}
                      <select
                        value={task.gitStatus}
                        onChange={e => onGitStatusChange(task.id, e.target.value)}
                        className={cn(
                          "inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg border border-transparent hover:border-black/10 dark:hover:border-white/10 focus:outline-none cursor-pointer appearance-none",
                          gitInfo.bg, gitInfo.color
                        )}
                      >
                        {Object.entries(GIT_STATUSES).map(([key, meta]) => (
                          <option key={key} value={key} className="bg-background text-foreground">{meta.label}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        <Pagination page={page} totalPages={totalPages} onChange={setPage} />
      </div>
    </div>
  );
}

function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (page: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-1.5 py-4">
      <button
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={page === 1}
        className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map(n => (
        <button
          key={n}
          onClick={() => onChange(n)}
          className={cn(
            "w-8 h-8 rounded-lg text-sm font-bold transition-colors",
            n === page ? "bg-primary text-primary-foreground" : "bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-muted-foreground"
          )}
        >
          {n}
        </button>
      ))}
      <button
        onClick={() => onChange(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}
