"use client";

import { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { FolderKanban, Search, LayoutGrid, Loader2, ChevronLeft, ChevronRight, ClipboardList, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { KanbanBoard } from "@/components/layout/KanbanBoard";
import { TaskDetailModal } from "@/components/projects/TaskDetailModal";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { apiFetch } from "@/lib/api/client";
import { Toast } from "@/components/ui/Toast";

// Django TaskAssignmentSerializer 응답 그대로 — 2026-09-07 컬럼 재설계로 필드명이 또 바뀌었다
// (task_title -> title, task_description -> description, due_date -> end_date, status ->
// status_code). Git 연동/에픽/난이도 등 새 필드는 이 화면에서 아직 안 씀.
type Task = {
  id: number;
  project: number | null;
  title: string;
  description: string | null;
  status_code: string;
  status_info: { code_id: string; code_name: string } | null;
  progress: number;
  start_date: string | null;
  end_date: string | null;
  assigned_user: number | null;
  assigned_user_name: string | null;
  reject_reason: string | null;
};

type Member = { id: string; name: string; email: string; role: string };

// Django TaskAssignment.Status 실제 값 — 예전 BACKLOG/DONE은 없고 REJECTED가 추가됐다.
const STATUSES = [
  { id: "PENDING_APPROVAL", label: "배분승인대기", color: "text-orange-500", bg: "bg-orange-500/10" },
  { id: "APPROVED", label: "승인됨", color: "text-sky-500", bg: "bg-sky-500/10" },
  { id: "IN_PROGRESS", label: "진행 중", color: "text-amber-500", bg: "bg-amber-500/10" },
  { id: "COMPLETED", label: "완료", color: "text-emerald-500", bg: "bg-emerald-500/10" },
  { id: "REJECTED", label: "반려됨", color: "text-red-500", bg: "bg-red-500/10" },
];

export default function TasksPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  // 대시보드 "업무 상태 분포" 차트에서 ?status=IN_PROGRESS 같은 링크로 들어오면 그 상태로 미리 필터링한다.
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  useEffect(() => {
    const s = searchParams.get("status");
    if (s) setStatusFilter(s);
  }, [searchParams]);

  // 일반유저는 "내 업무"가 기본값 — 전체 업무 조회는 PM만 필요하다는 판단
  const [filterScope, setFilterScope] = useState<"ME" | "ALL">("ME");
  const [viewMode, setViewMode] = useState<"KANBAN" | "LIST" | "WBS">("LIST");
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 10;

  // 리스트/WBS 뷰 행을 눌러도 아무 반응이 없었다 — 칸반 카드와 동일하게 상세 모달을 연다.
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<Task | null>(null);
  const [toast, setToast] = useState<{ message: string; variant: "success" | "error" } | null>(null);

  // TanStack Query 도입 전에는 화면에 들어올 때마다 useEffect로 다시 fetch하고 로딩 스피너부터
  // 띄웠다 — 다른 화면 갔다가 돌아올 때마다 매번 깜빡였다. staleTime(30초) 안에서는 캐시를
  // 그대로 보여주고, 지난 뒤에는 화면은 그대로 둔 채 백그라운드에서 조용히 갱신한다
  // (isLoading=최초 로드만 true, isFetching=백그라운드 갱신 포함) — 예전의 "silent refetch"
  // 수동 처리를 라이브러리가 대신해준다.
  // refetchInterval: PM이 다른 화면에서 승인/반려하거나 동료가 상태를 바꿔도, 지금까지는
  // 내가 직접 새로고침하기 전까진 안 보였다(NotificationBell만 30초 폴링하고 있었음).
  // 같은 주기로 업무 목록도 백그라운드에서 갱신해 "거의 실시간"에 가깝게 만든다 — 진짜
  // 실시간(웹소켓 푸시)은 백엔드 지원이 필요해 별도.
  // isError: 최초 로드 실패 시 tasks가 기본값 []로 남는데, isLoading만 보면 "로딩 끝났으니
  // 빈 배열이 곧 진짜 데이터"로 취급돼 "업무가 없습니다"가 뜬다 — 실제로는 조회가 실패한
  // 것뿐인데 업무가 통째로 사라진 것처럼 보이는 문제라 별도로 에러 화면을 보여준다.
  const { data: tasks = [], isLoading: loading, isError: tasksError } = useQuery({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/tasks/assignments/"),
    refetchInterval: 30_000,
  });

  // 프로젝트 멤버 목록 — 다른 화면(칸반보드 등)도 같은 쿼리 키를 쓰면 캐시를 공유해서
  // 화면을 오갈 때마다 다시 안 부른다.
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiFetch<any[]>("/api/projects/"),
  });
  const { data: usersData } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiFetch<any[]>("/api/users/"),
  });
  const currentProjectId = projectsData?.[0] ? String(projectsData[0].id) : null;
  // 칸반 담당자 드롭다운엔 실제로 업무를 받을 수 있는 사람만 — PM(is_staff)은 배정 대상이
  // 아니고, 온보딩 전이라 이름이 비어있는 계정도 빈 옵션으로 보이니 제외한다.
  const members: Member[] = useMemo(
    () =>
      (usersData ?? [])
        .filter((u: any) => !u.is_staff && (u.first_name || u.last_name))
        .map((u: any) => ({
          id: String(u.id),
          name: `${u.last_name ?? ""}${u.first_name ?? ""}`.trim() || u.username,
          email: u.email,
          role: u.is_staff ? "PM" : "MEMBER",
        })),
    [usersData]
  );

  // 로그인 정보가 로드된 뒤 역할에 맞는 기본 필터로 맞춘다 (PM은 전체 업무를 기본으로 봄)
  useEffect(() => {
    if (isPM) setFilterScope("ALL");
    else setFilterScope("ME");
  }, [isPM]);

  const statusMutation = useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: number; newStatus: string }) =>
      apiFetch(`/api/tasks/assignments/${taskId}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: newStatus }),
      }),
    onMutate: ({ taskId }) => setProcessingId(taskId),
    onSuccess: (_data, { taskId, newStatus }) => {
      queryClient.setQueryData<Task[]>(["tasks"], (prev) =>
        prev?.map(t => t.id === taskId ? { ...t, status_code: newStatus } : t)
      );
    },
    onError: () => setToast({ message: "상태 변경에 실패했습니다.", variant: "error" }),
    onSettled: () => setProcessingId(null),
  });
  const handleStatusChange = (taskId: number, newStatus: string) =>
    statusMutation.mutate({ taskId, newStatus });

  const filteredTasks = useMemo(() => {
    let filtered = tasks;
    if (filterScope === "ME" && user) {
      filtered = filtered.filter(t => String(t.assigned_user) === String(user.id));
    }
    if (statusFilter) {
      filtered = filtered.filter(t => t.status_code === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(t =>
        t.title.toLowerCase().includes(q) ||
        (t.assigned_user_name || "").toLowerCase().includes(q)
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
              placeholder="업무명, 담당자 검색..."
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

      {/* 대시보드 "업무 상태 분포"에서 상태를 지정해 들어왔을 때만 보이는 필터 표시 */}
      {statusFilter && (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-primary/10 text-primary">
            상태: {STATUSES.find(s => s.id === statusFilter)?.label ?? statusFilter}
            <button onClick={() => setStatusFilter(null)} className="hover:opacity-70 transition-opacity" aria-label="필터 해제">
              ×
            </button>
          </span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-primary/50" />
        </div>
      ) : tasksError ? (
        <div className="flex flex-col items-center justify-center h-64 text-center gap-3">
          <AlertTriangle className="w-10 h-10 text-red-500/50" />
          <p className="text-muted-foreground text-sm">업무 목록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</p>
        </div>
      ) : (
        <>
          {viewMode === "KANBAN" ? (
            currentProjectId ? (
              <KanbanBoard
                projectId={currentProjectId}
                initialTasks={filteredTasks}
                members={members}
                onTaskChange={(taskId, patch) => queryClient.setQueryData<Task[]>(["tasks"], prev => prev?.map(t => t.id === taskId ? { ...t, ...patch } : t))}
              />
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
                      const statusInfo = STATUSES.find(s => s.id === task.status_code) || STATUSES[0];
                      const overdue = isTaskOverdue({ wbsEnd: task.end_date, status: task.status_code });
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
                            {task.status_code === "PENDING_APPROVAL" ? (
                              <span className={cn("inline-block text-xs font-bold px-2.5 py-1.5 rounded-lg", statusInfo.bg, statusInfo.color)}>
                                {statusInfo.label} · PM 승인 대기
                              </span>
                            ) : (
                              <select
                                value={task.status_code}
                                onChange={e => handleStatusChange(task.id, e.target.value)}
                                disabled={processingId === task.id}
                                className={cn(
                                  "text-xs font-bold px-2.5 py-1.5 rounded-lg border border-transparent hover:border-black/10 dark:hover:border-white/10 focus:outline-none transition-all cursor-pointer appearance-none",
                                  statusInfo.bg, statusInfo.color
                                )}
                              >
                                {STATUSES.filter(s => s.id !== "PENDING_APPROVAL" && s.id !== "REJECTED").map(s => <option key={s.id} value={s.id} className="bg-background text-foreground">{s.label}</option>)}
                              </select>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            {task.assigned_user_name ? (
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-[10px] font-bold">
                                  {task.assigned_user_name.charAt(0)}
                                </div>
                                <span className="font-medium text-[13px]">{task.assigned_user_name}</span>
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-[13px]">미배정</span>
                            )}
                          </td>
                          <td className={cn("px-6 py-4 text-[13px]", overdue ? "text-red-500 font-semibold" : "text-muted-foreground")}>
                            <div className="flex items-center gap-1">
                              {overdue && <AlertTriangle className="w-3.5 h-3.5 shrink-0" />}
                              {task.end_date ? new Date(task.end_date).toLocaleDateString() : "-"}
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
            <WbsBoardView tasks={filteredTasks} onRowClick={setSelectedTaskForDetail} />
          )}
        </>
      )}

      {selectedTaskForDetail && (
        <TaskDetailModal
          task={selectedTaskForDetail}
          members={members}
          onClose={() => setSelectedTaskForDetail(null)}
          onUpdated={(updated) => {
            queryClient.setQueryData<Task[]>(["tasks"], prev => prev?.map(t => t.id === updated.id ? { ...t, ...updated } : t));
            setSelectedTaskForDetail(null);
          }}
        />
      )}
      <Toast message={toast?.message ?? null} variant={toast?.variant} onDismiss={() => setToast(null)} />
    </div>
  );
}

/**
 * 업무보드(WBS) 뷰 — 상단에는 상태별 카운트/전체 진행률 요약 바를, 아래에는 업무별 표를 그린다.
 * Git 상태 배지/예상 소요시간/난이도는 heyzzabi2 시절 필드로 이 프로젝트 백엔드엔 없어서 제외했다.
 */
function WbsBoardView({ tasks, onRowClick }: { tasks: Task[]; onRowClick: (task: Task) => void }) {
  const total = tasks.length;
  const counts = STATUSES.reduce((acc, s) => {
    acc[s.id] = tasks.filter(t => t.status_code === s.id).length;
    return acc;
  }, {} as Record<string, number>);
  const doneCount = counts["COMPLETED"] ?? 0;
  const overallProgress = total > 0 ? Math.round((doneCount / total) * 100) : 0;

  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);
  useEffect(() => { setPage(1); }, [tasks]);
  const totalPages = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE));
  const pagedTasks = tasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      {/* 전체 진행상황 요약 */}
      <div className="bg-card rounded-2xl border border-border p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-muted-foreground">전체 진행률</h3>
          <span className="text-sm font-black text-primary">{overallProgress}% ({doneCount}/{total}건 완료)</span>
        </div>
        <div className="w-full h-2.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden mb-4">
          <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${overallProgress}%` }} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {STATUSES.map(s => (
            <div key={s.id} className={cn("rounded-xl p-3", s.bg)}>
              <p className={cn("text-xs font-bold", s.color)}>{s.label}</p>
              <p className="text-xl font-black mt-1">{counts[s.id] ?? 0}건</p>
            </div>
          ))}
        </div>
      </div>

      {/* 업무별 WBS 표 */}
      <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-sm">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-6 py-4 font-bold">업무명</th>
              <th className="px-6 py-4 font-bold">담당자</th>
              <th className="px-6 py-4 font-bold">상태</th>
              <th className="px-6 py-4 font-bold text-center">진행률</th>
              <th className="px-6 py-4 font-bold">마감일</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 dark:divide-white/5">
            {tasks.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">조건에 맞는 업무가 없습니다.</td></tr>
            ) : (
              pagedTasks.map(task => {
                const statusInfo = STATUSES.find(s => s.id === task.status_code) || STATUSES[0];
                const overdue = isTaskOverdue({ wbsEnd: task.end_date, status: task.status_code });
                return (
                  <tr
                    key={task.id}
                    onClick={() => onRowClick(task)}
                    className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold">{task.title}</span>
                        {overdue && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-500 shrink-0">
                            <AlertTriangle className="w-3 h-3" /> 지연
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-[13px]">{task.assigned_user_name ? task.assigned_user_name : <span className="text-muted-foreground">미배정</span>}</td>
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
                    <td className="px-6 py-4 text-[13px] text-muted-foreground">
                      {task.end_date ? new Date(task.end_date).toLocaleDateString() : "-"}
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
