"use client";

import { useState, useEffect } from "react";
import { MoreHorizontal, Plus, CheckCircle2, XCircle, UserPlus, Loader2, X, MessageSquare, Sparkles, ExternalLink, AlertTriangle } from "lucide-react";
import { AgentBadge } from "@/components/ui/AgentBadge";
import { cn } from "@/lib/utils";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { DndContext, DragOverlay, closestCorners, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { TaskDetailModal } from "../projects/TaskDetailModal";
import { useAuth } from "@/lib/auth";

// 파이프라인: 대기(미배정) -> 배분승인대기(담당자 지정, PM 승인 필요) -> 진행 중 -> 완료 (FR-05-005, FR-05-018~021)
const COLUMNS = [
  { id: "BACKLOG", title: "대기", color: "bg-muted" },
  { id: "PENDING_APPROVAL", title: "배분승인대기", color: "bg-orange-500/20" },
  { id: "IN_PROGRESS", title: "진행 중", color: "bg-primary/20" },
  { id: "DONE", title: "완료", color: "bg-emerald-500/20" },
];

function AssigneeDropdown({ task, members, onAssign, readOnly }: { task: any, members: any[], onAssign: (taskId: string, userId: string) => void, readOnly?: boolean }) {
  const [isOpen, setIsOpen] = useState(false);

  // 담당자 재배정은 PM의 권한 — 일반 유저에게는 클릭해도 아무 일도 안 일어나는 뱃지로만 보여준다
  if (readOnly) {
    return (
      <span className="bg-black/5 dark:bg-white/5 text-muted-foreground px-2 py-1 rounded-md font-medium truncate max-w-[120px] inline-block">
        {task.assignee ? task.assignee.name : "미배정"}
      </span>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
        className="bg-primary/10 text-primary px-2 py-1 rounded-md font-medium truncate max-w-[120px] hover:bg-primary/20 transition-colors flex items-center gap-1"
      >
        {task.assignee ? task.assignee.name : <><UserPlus className="w-3 h-3" /> 할당</>}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setIsOpen(false); }} />
          <div className="absolute left-0 mt-1 w-40 bg-card border border-border rounded-lg shadow-xl z-50 overflow-hidden">
            <div className="p-2 text-xs font-semibold text-muted-foreground bg-muted/50">담당자 지정</div>
            <div className="max-h-48 overflow-y-auto">
              {members.map(member => (
                <button
                  key={member.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    onAssign(task.id, member.id);
                    setIsOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors font-medium"
                >
                  {member.name}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SortableTask({ task, members, onAssign, onClick, isPM, onApprove, onReject, onRequestAssignment, processing, currentUserId }: any) {
  // 칸반 카드를 드래그해 상태를 바꾸는 것도 "내 업무" 아니면 PM만 — 예전엔 아무 카드나 아무나 옮길 수 있었다.
  const canManage = isPM || task.assigneeId === currentUserId;
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id, data: { type: "Task", task }, disabled: !canManage });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const showApprovalActions = isPM && task.status === "PENDING_APPROVAL";

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...(canManage ? attributes : {})}
      {...(canManage ? listeners : {})}
      onClick={() => onClick(task)}
      className={cn(
        "bg-white dark:bg-white/5 hover:bg-zinc-50 dark:hover:bg-white/10 border border-zinc-200 dark:border-white/10 shadow-sm hover:shadow-md rounded-lg p-4 transition-all group relative",
        canManage ? "cursor-grab active:cursor-grabbing" : "cursor-pointer",
        isDragging && "opacity-50 border-primary shadow-lg ring-2 ring-primary/20"
      )}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-1.5">
          {isTaskOverdue(task) && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-500">
              <AlertTriangle className="w-3 h-3" /> 지연
            </span>
          )}
        </div>
        <button className="text-transparent group-hover:text-muted-foreground hover:!text-foreground">
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>
      <h4 className="font-medium text-sm leading-tight mb-3">{task.title}</h4>

      {task.status === "BACKLOG" && task.rejectReason && (
        <p className="text-[11px] text-red-400 mb-3 line-clamp-2">배분 반려됨: {task.rejectReason}</p>
      )}

      {/* 칸반에서 멈춰있는 걸 보고도 사이드바에서 승인함을 따로 찾아가야 했다 — 카드에서 바로 이동 */}
      {task.status === "PENDING_APPROVAL" && (
        <Link
          href="/approvals"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 text-[11px] text-orange-500 hover:text-orange-400 font-medium mb-2"
        >
          <ExternalLink className="w-3 h-3" /> 승인함에서 보기
        </Link>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-border pt-3 mt-3">
        <AssigneeDropdown task={task} members={members} onAssign={onAssign} readOnly={!isPM} />
        {task.progress > 0 && <span className="font-medium text-primary">{task.progress}%</span>}
      </div>

      {task.status === "BACKLOG" && (
        <button
          onClick={(e) => { e.stopPropagation(); onRequestAssignment(task); }}
          className="w-full mt-3 flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-primary/10 text-primary hover:bg-primary/20 text-xs font-semibold transition-colors"
        >
          <UserPlus className="w-3.5 h-3.5" /> 배분 승인 요청
        </button>
      )}

      {showApprovalActions && (
        <div className="flex items-center gap-2 border-t border-border pt-3 mt-3" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onReject(task)}
            disabled={processing === task.id}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-red-500/10 text-red-400 hover:bg-red-500/20 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <XCircle className="w-3.5 h-3.5" /> 반려
          </button>
          <button
            onClick={() => onApprove(task)}
            disabled={processing === task.id}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            {processing === task.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} 승인
          </button>
        </div>
      )}
    </div>
  );
}

function KanbanColumn({ column, tasks, members, onAssign, onCardClick, projectId, isPM, onApprove, onReject, onRequestAssignment, processing, currentUserId }: any) {
  const { setNodeRef } = useSortable({
    id: column.id,
    data: { type: "Column", column },
  });

  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const router = useRouter();

  const handleCreate = async () => {
    if (!newTitle.trim()) {
      setIsCreating(false);
      return;
    }

    setIsSaving(true);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTitle,
          status: column.id,
          projectId
        })
      });
      if (res.ok) {
        setNewTitle("");
        setIsCreating(false);
        router.refresh();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="w-full min-w-0 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-lg rounded-xl flex flex-col overflow-hidden">
      <div className="p-3 border-b border-border flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-800/50 shrink-0">
        <div className="flex items-center gap-2">
          <div className={cn("w-3 h-3 rounded-full", column.color)} />
          <h3 className="font-semibold text-sm">{column.title}</h3>
          <span className="text-xs bg-black/10 dark:bg-white/10 px-2 py-0.5 rounded-full text-muted-foreground">
            {tasks.length}
          </span>
        </div>
        {column.id === "BACKLOG" && (
          <button onClick={() => setIsCreating(true)} className="text-muted-foreground hover:text-foreground p-1 hover:bg-black/10 dark:hover:bg-white/10 rounded transition-colors">
            <Plus className="w-4 h-4" />
          </button>
        )}
      </div>

      <div ref={setNodeRef} className="flex-1 p-3 space-y-3 min-h-[200px]">
        {isCreating && (
          <div className="bg-zinc-50/50 dark:bg-white/5 border border-primary/50 rounded-lg p-3">
            <input
              autoFocus
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate();
                if (e.key === "Escape") setIsCreating(false);
              }}
              placeholder="업무 제목..."
              className="w-full bg-transparent outline-none text-sm font-medium"
            />
            <div className="flex justify-end gap-2 mt-2">
              <button onClick={() => setIsCreating(false)} className="text-xs text-muted-foreground hover:text-foreground">취소</button>
              <button onClick={handleCreate} disabled={isSaving} className="text-xs bg-primary text-primary-foreground px-2 py-1 rounded">
                {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : "추가"}
              </button>
            </div>
          </div>
        )}

        <SortableContext items={tasks.map((t: any) => t.id)} strategy={verticalListSortingStrategy}>
          {tasks.map((task: any) => (
            <SortableTask
              key={task.id}
              task={task}
              members={members}
              onAssign={onAssign}
              onClick={onCardClick}
              isPM={isPM}
              onApprove={onApprove}
              onReject={onReject}
              onRequestAssignment={onRequestAssignment}
              processing={processing}
              currentUserId={currentUserId}
            />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}

export function KanbanBoard({ projectId, initialTasks, members = [] }: { projectId: string, initialTasks: any[], members?: any[] }) {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [tasks, setTasks] = useState(initialTasks);
  const [activeTask, setActiveTask] = useState<any | null>(null);
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<any | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);

  // FR-05-021: 담당자 지정이 필요한 상태 변경(배분승인대기 진입)은 즉시 반영하지 않고 확인 절차를 거침
  const [assignConfirm, setAssignConfirm] = useState<{ task: any; assigneeId: string } | null>(null);
  const [rejectTarget, setRejectTarget] = useState<any | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // FR-05-016/017: AI 담당자 추천 (기술 적합도 · 업무 여유도 · 유사 업무 경험 근거 포함)
  const [aiRecs, setAiRecs] = useState<any[] | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const handleAssign = async (taskId: string, userId: string) => {
    const selectedUser = members.find(m => m.id === userId);
    // 수동으로 담당자를 바꾸는 것이므로, 이전 담당자에 대한 AI 배정 근거는 더 이상 유효하지 않다 — 함께 지운다
    setTasks(prev => prev.map(t =>
      t.id === taskId ? { ...t, assigneeId: userId, assignee: selectedUser, assignmentReason: null } : t
    ));

    try {
      await fetch(`/api/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assigneeId: userId, assignmentReason: null })
      });
    } catch (error) {
      console.error('Failed to assign task:', error);
    }
  };

  const commitStatusChange = async (taskId: string, newStatus: string, extra: Record<string, any> = {}) => {
    setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: newStatus, ...extra } : t));
    try {
      await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, ...extra }),
      });
    } catch (e) {
      console.error("Failed to update status", e);
    }
  };

  const handleDragStart = (event: any) => {
    const { active } = event;
    const task = tasks.find(t => t.id === active.id);
    if (task) setActiveTask(task);
  };

  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    setActiveTask(null);
    if (!over) return;

    const activeId = active.id;
    const overId = over.id;
    if (activeId === overId) return;

    const draggedTask = tasks.find(t => t.id === activeId);
    const overColumnId = COLUMNS.find(c => c.id === overId)?.id || tasks.find(t => t.id === overId)?.status;
    if (!draggedTask || !overColumnId || draggedTask.status === overColumnId) return;
    // useSortable의 disabled로 이미 막지만, 한 번 더 확인 — 남의 업무는 PM이 아니면 옮길 수 없다
    if (!isPM && draggedTask.assigneeId !== user?.id) return;

    if (overColumnId === "PENDING_APPROVAL") {
      // 담당자 확인 없이는 배분승인대기로 보낼 수 없음 — 확인 모달을 띄우고 실제 상태는 아직 바꾸지 않음
      openAssignConfirm(draggedTask);
      return;
    }

    commitStatusChange(activeId, overColumnId);
  };

  const openAssignConfirm = async (task: any) => {
    setAssignConfirm({ task, assigneeId: task.assigneeId || "" });
    setAiRecs(null);
    setAiLoading(true);
    try {
      const res = await fetch(`/api/tasks/${task.id}/recommend-assignees`, { method: "POST" });
      const data = await res.json();
      if (res.ok) setAiRecs(data.recommendations || []);
    } catch (e) {
      console.error("Failed to fetch AI recommendations", e);
    } finally {
      setAiLoading(false);
    }
  };

  const handleConfirmAssign = () => {
    if (!assignConfirm || !assignConfirm.assigneeId) return;
    const assignee = members.find(m => m.id === assignConfirm.assigneeId);
    // 고른 담당자가 AI 추천 목록에 있던 사람이면 그 근거를 그대로 남기고, 직접 고른 사람이면(추천에 없던 사람) 지운다
    const rec = aiRecs?.find(r => r.userId === assignConfirm.assigneeId);
    const assignmentReason = rec
      ? JSON.stringify({ fitScore: rec.fitScore, techFit: rec.techFit, workloadFit: rec.workloadFit, experienceFit: rec.experienceFit })
      : null;
    commitStatusChange(assignConfirm.task.id, "PENDING_APPROVAL", {
      assigneeId: assignConfirm.assigneeId,
      assignee,
      rejectReason: null,
      assignmentReason,
    });
    setAssignConfirm(null);
  };

  const handleApprove = async (task: any) => {
    setProcessing(task.id);
    try {
      const res = await fetch(`/api/tasks/${task.id}/approve`, { method: "POST" });
      if (res.ok) setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: "IN_PROGRESS", rejectReason: null } : t));
    } finally {
      setProcessing(null);
    }
  };

  const handleReject = async () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    setProcessing(rejectTarget.id);
    try {
      const res = await fetch(`/api/tasks/${rejectTarget.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (res.ok) {
        setTasks(prev => prev.map(t => t.id === rejectTarget.id ? { ...t, status: "BACKLOG", assigneeId: null, assignee: null, rejectReason } : t));
        setRejectTarget(null);
        setRejectReason("");
      }
    } finally {
      setProcessing(null);
    }
  };

  // Sync state when props change
  useEffect(() => { setTasks(initialTasks) }, [initialTasks]);

  return (
    <>
      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        {/* 컬럼 4개가 가로 스크롤 없이 화면 폭에 맞춰 균등하게 나뉘도록 grid로 배치 — 완료 컬럼까지 한 화면에 다 보이게.
            높이를 여기서 가두지 않는다 — 예전엔 부모가 h-[70vh]로 고정하고 각 컬럼이 그 안에서 따로
            스크롤됐는데(칸마다 스크롤바), 그러면 카드가 많은 칸은 잘려 보이고 스크롤도 4번 따로 해야 했다.
            내용 높이만큼 자연스럽게 늘어나게 하고, 스크롤은 페이지 전체(오른쪽 하나)에 맡긴다. */}
        <div className="w-full pb-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
            <SortableContext items={COLUMNS.map((c) => c.id)}>
              {COLUMNS.map((col) => (
                <KanbanColumn
                  key={col.id}
                  column={col}
                  projectId={projectId}
                  tasks={tasks.filter((t) => t.status === col.id)}
                  members={members}
                  onAssign={handleAssign}
                  onCardClick={(t: any) => setSelectedTaskForDetail(t)}
                  isPM={isPM}
                  onApprove={handleApprove}
                  onReject={(t: any) => setRejectTarget(t)}
                  onRequestAssignment={openAssignConfirm}
                  processing={processing}
                  currentUserId={user?.id}
                />
              ))}
            </SortableContext>
          </div>
        </div>
        <DragOverlay>
          {activeTask ? <SortableTask task={activeTask} members={members} onAssign={handleAssign} onClick={() => {}} isPM={isPM} processing={processing} currentUserId={user?.id} /> : null}
        </DragOverlay>
      </DndContext>

      {selectedTaskForDetail && (
        <TaskDetailModal
          task={selectedTaskForDetail}
          members={members}
          onClose={() => setSelectedTaskForDetail(null)}
        />
      )}

      {/* 배분승인대기 진입 확인 모달 (FR-05-021) */}
      {assignConfirm && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-lg w-full mx-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-primary" /> 담당자 배정 확인
              </h3>
              <button onClick={() => setAssignConfirm(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              <span className="font-semibold text-foreground">"{assignConfirm.task.title}"</span> 업무를 담당자에게 배정하고 PM 승인을 요청합니다.
            </p>

            <div className="mb-5">
              <label className="flex items-center gap-1.5 text-sm font-semibold mb-2">
                <Sparkles className="w-4 h-4 text-primary" /> 추천 담당자
                <AgentBadge agent="taskAssign" />
              </label>
              {aiLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                  <Loader2 className="w-4 h-4 animate-spin" /> 기술스택·업무량·경험을 분석하는 중...
                </div>
              ) : !aiRecs || aiRecs.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">추천할 만한 근거가 부족합니다. 아래에서 직접 선택해주세요.</p>
              ) : (
                <div className="space-y-2">
                  {aiRecs.map((r: any) => (
                    <button
                      key={r.userId}
                      onClick={() => setAssignConfirm({ ...assignConfirm, assigneeId: r.userId })}
                      className={cn(
                        "w-full text-left p-3 rounded-xl border transition-colors",
                        assignConfirm.assigneeId === r.userId ? "border-primary bg-primary/5" : "border-border hover:bg-black/5 dark:hover:bg-white/5"
                      )}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-semibold text-sm">{r.name}</span>
                        <span className="text-[11px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full">적합도 {r.fitScore}</span>
                      </div>
                      <ul className="text-[11px] text-muted-foreground space-y-0.5">
                        <li>🛠 기술: {r.techFit}</li>
                        <li>📊 여유도: {r.workloadFit} (현재 진행 {r.currentActiveTasks}건)</li>
                        <li>📁 경험: {r.experienceFit}</li>
                      </ul>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <label className="block text-sm font-medium mb-1.5">직접 선택</label>
            <select
              value={assignConfirm.assigneeId}
              onChange={(e) => setAssignConfirm({ ...assignConfirm, assigneeId: e.target.value })}
              className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 mb-6 appearance-none"
            >
              <option value="" disabled>담당자 선택</option>
              {members.map((m: any) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <div className="flex gap-3">
              <button onClick={() => setAssignConfirm(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleConfirmAssign}
                disabled={!assignConfirm.assigneeId}
                className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50"
              >
                배정 요청
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 배분 반려 사유 입력 모달 (FR-05-019) */}
      {rejectTarget && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <XCircle className="w-5 h-5" /> 배분 반려
              </h3>
              <button onClick={() => setRejectTarget(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              <span className="font-semibold text-foreground">"{rejectTarget.title}"</span> 배정을 반려합니다. 업무는 대기 상태로 돌아갑니다.
            </p>
            <div className="relative mb-4">
              <MessageSquare className="w-4 h-4 absolute left-3 top-3.5 text-muted-foreground" />
              <textarea
                autoFocus
                className="w-full pl-9 pr-4 py-3 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 resize-none h-24"
                placeholder="반려 사유를 입력해주세요."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <button onClick={() => setRejectTarget(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim() || processing === rejectTarget.id}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {processing === rejectTarget.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />} 반려 처리
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
