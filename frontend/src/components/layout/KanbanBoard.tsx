"use client";

import { useState, useEffect } from "react";
import { MoreHorizontal, CheckCircle2, XCircle, UserPlus, Loader2, X, MessageSquare, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { DndContext, DragOverlay, closestCorners, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { TaskDetailModal } from "../projects/TaskDetailModal";
import { useAuth } from "@/lib/auth";
import { Toast } from "@/components/ui/Toast";
import { apiFetch } from "@/lib/api/client";

// 2026-09-01: Django TaskAssignment의 실제 상태값에 맞게 재배선했다. heyzzabi2 시절엔
// 대기(미배정)->배분승인대기->진행중->완료 4단계였는데, Django에서는 업무가 자동배정
// (auto-assign) 시점에 이미 담당자가 정해진 채로 "승인대기"에서 시작한다 — 미배정
// 대기(BACKLOG) 개념 자체가 없다. 대신 반려(REJECTED)가 별도 종결 상태로 존재한다.
const COLUMNS = [
  { id: "PENDING_APPROVAL", title: "승인 대기", color: "bg-orange-500/20" },
  { id: "IN_PROGRESS", title: "진행 중", color: "bg-primary/20" },
  { id: "COMPLETED", title: "완료", color: "bg-emerald-500/20" },
  { id: "REJECTED", title: "반려됨", color: "bg-red-500/20" },
];

function AssigneeBadge({ task, members, onAssign, readOnly }: { task: any; members: any[]; onAssign: (taskId: number, userId: string) => void; readOnly?: boolean }) {
  const [isOpen, setIsOpen] = useState(false);

  // 담당자 재배정은 PM의 권한 — 일반 유저에게는 클릭해도 아무 일도 안 일어나는 뱃지로만 보여준다
  if (readOnly) {
    return (
      <span className="bg-black/5 dark:bg-white/5 text-muted-foreground px-2 py-1 rounded-md font-medium truncate max-w-[120px] inline-block">
        {task.assigned_user_name || "미배정"}
      </span>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
        className="bg-primary/10 text-primary px-2 py-1 rounded-md font-medium truncate max-w-[120px] hover:bg-primary/20 transition-colors flex items-center gap-1"
      >
        {task.assigned_user_name || <><UserPlus className="w-3 h-3" /> 미배정</>}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setIsOpen(false); }} />
          <div className="absolute left-0 mt-1 w-40 bg-card border border-border rounded-lg shadow-xl z-50 overflow-hidden">
            <div className="p-2 text-xs font-semibold text-muted-foreground bg-muted/50">담당자 재배정</div>
            <div className="max-h-48 overflow-y-auto">
              {members.map((member: any) => (
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

function SortableTask({ task, members, onAssign, onClick, isPM, onApprove, onReject, processing, currentUserId }: any) {
  // 칸반 카드를 드래그해 상태를 바꾸는 것도 "내 업무" 아니면 PM만 — 예전엔 아무 카드나 아무나 옮길 수 있었다.
  const canManage = isPM || String(task.assigned_user) === String(currentUserId);
  // 승인대기/반려 상태는 드래그로 옮길 수 없다 — 승인/반려 버튼으로만 상태가 바뀐다.
  const draggable = canManage && task.status !== "PENDING_APPROVAL" && task.status !== "REJECTED";
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id, data: { type: "Task", task }, disabled: !draggable });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const showApprovalActions = isPM && task.status === "PENDING_APPROVAL";
  const overdue = isTaskOverdue({ wbsEnd: task.due_date, status: task.status });

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...(draggable ? attributes : {})}
      {...(draggable ? listeners : {})}
      onClick={() => onClick(task)}
      className={cn(
        "bg-white dark:bg-white/5 hover:bg-zinc-50 dark:hover:bg-white/10 border border-zinc-200 dark:border-white/10 shadow-sm hover:shadow-md rounded-lg p-4 transition-all group relative",
        draggable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer",
        isDragging && "opacity-50 border-primary shadow-lg ring-2 ring-primary/20"
      )}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-1.5">
          {overdue && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-500">
              <AlertTriangle className="w-3 h-3" /> 지연
            </span>
          )}
        </div>
        <button className="text-transparent group-hover:text-muted-foreground hover:!text-foreground">
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>
      <h4 className="font-medium text-sm leading-tight mb-1">{task.task_title}</h4>
      <p className="text-[11px] text-muted-foreground mb-3">{task.req_code} {task.req_name}</p>

      {task.status === "REJECTED" && task.reject_reason && (
        <p className="text-[11px] text-red-400 mb-3 line-clamp-2">반려됨: {task.reject_reason}</p>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-border pt-3 mt-3">
        <AssigneeBadge task={task} members={members} onAssign={onAssign} readOnly={!isPM} />
        {task.progress > 0 && <span className="font-medium text-primary">{task.progress}%</span>}
      </div>

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

function KanbanColumn({ column, tasks, members, onAssign, onCardClick, isPM, onApprove, onReject, processing, currentUserId }: any) {
  const { setNodeRef } = useSortable({
    id: column.id,
    data: { type: "Column", column },
  });

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
      </div>

      <div ref={setNodeRef} className="flex-1 p-3 space-y-3 min-h-[200px]">
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
              processing={processing}
              currentUserId={currentUserId}
            />
          ))}
          {tasks.length === 0 && (
            <p className="text-center text-xs text-muted-foreground py-8">업무가 없습니다.</p>
          )}
        </SortableContext>
      </div>
    </div>
  );
}

export function KanbanBoard({ initialTasks, members = [], onTaskChange }: { projectId?: string; initialTasks: any[]; members?: any[]; onTaskChange?: (taskId: number, patch: Record<string, any>) => void }) {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [tasks, setTasks] = useState(initialTasks);
  const [activeTask, setActiveTask] = useState<any | null>(null);
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<any | null>(null);
  const [processing, setProcessing] = useState<number | null>(null);
  const [rejectTarget, setRejectTarget] = useState<any | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const handleAssign = async (taskId: number, userId: string) => {
    const prev = tasks;
    const selectedMember = members.find((m: any) => m.id === userId);
    const patch = { assigned_user: userId, assigned_user_name: selectedMember?.name };
    setTasks((cur) => cur.map((t) => t.id === taskId ? { ...t, ...patch } : t));
    onTaskChange?.(taskId, patch);
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify({ assigned_user: userId }),
      });
    } catch (e) {
      console.error("담당자 재배정 실패", e);
      setTasks(prev);
      onTaskChange?.(taskId, prev.find((t) => t.id === taskId) ?? {});
    }
  };

  const commitStatusChange = async (taskId: number, newStatus: string) => {
    const prev = tasks;
    setTasks((cur) => cur.map((t) => t.id === taskId ? { ...t, status: newStatus } : t));
    onTaskChange?.(taskId, { status: newStatus });
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
    } catch (e) {
      console.error("상태 변경 실패", e);
      setTasks(prev);
      onTaskChange?.(taskId, { status: prev.find((t) => t.id === taskId)?.status });
    }
  };

  const handleDragStart = (event: any) => {
    const { active } = event;
    const task = tasks.find((t) => t.id === active.id);
    if (task) setActiveTask(task);
  };

  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    setActiveTask(null);
    if (!over) return;

    const activeId = active.id;
    const overId = over.id;
    if (activeId === overId) return;

    const draggedTask = tasks.find((t) => t.id === activeId);
    const overColumnId = COLUMNS.find((c) => c.id === overId)?.id || tasks.find((t) => t.id === overId)?.status;
    if (!draggedTask || !overColumnId || draggedTask.status === overColumnId) return;
    // useSortable의 disabled로 이미 막지만, 한 번 더 확인 — 남의 업무는 PM이 아니면 옮길 수 없다
    if (!isPM && String(draggedTask.assigned_user) !== String(user?.id)) return;
    // 승인대기/반려로는 드래그로 못 들어간다 — 승인/반려 버튼 또는 서버 로직으로만 전이된다
    if (overColumnId === "PENDING_APPROVAL" || overColumnId === "REJECTED") return;

    commitStatusChange(activeId, overColumnId);
  };

  const handleApprove = async (task: any) => {
    setProcessing(task.id);
    try {
      await apiFetch(`/api/tasks/assignments/${task.id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status: "APPROVED" }),
      });
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "APPROVED", reject_reason: null } : t));
      onTaskChange?.(task.id, { status: "APPROVED", reject_reason: null });
      setToastMessage("업무가 승인되었습니다");
    } catch (e: any) {
      alert(e.message || "승인에 실패했습니다.");
    } finally {
      setProcessing(null);
    }
  };

  const handleReject = async () => {
    if (!rejectTarget || !rejectReason.trim()) return;
    setProcessing(rejectTarget.id);
    try {
      await apiFetch(`/api/tasks/assignments/${rejectTarget.id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status: "REJECTED", reject_reason: rejectReason }),
      });
      setTasks((prev) => prev.map((t) => t.id === rejectTarget.id ? { ...t, status: "REJECTED", reject_reason: rejectReason } : t));
      onTaskChange?.(rejectTarget.id, { status: "REJECTED", reject_reason: rejectReason });
      setRejectTarget(null);
      setRejectReason("");
      setToastMessage("업무가 반려되었습니다");
    } catch (e: any) {
      alert(e.message || "반려에 실패했습니다.");
    } finally {
      setProcessing(null);
    }
  };

  // Sync state when props change
  useEffect(() => { setTasks(initialTasks) }, [initialTasks]);

  // 승인됨(APPROVED)은 화면에 별도 컬럼을 안 두고 "진행 중" 칸에 같이 보여준다 — 승인만 되고
  // 아직 진행 상태로 안 옮겨진 업무가 승인대기 칸에도 진행 칸에도 안 보여 사라진 것처럼 보이는
  // 문제를 피하기 위함(담당자가 드래그로 직접 진행 중으로 옮기기 전까지의 과도 상태).
  const columnTasks = (columnId: string) =>
    tasks.filter((t) => columnId === "IN_PROGRESS" ? (t.status === "IN_PROGRESS" || t.status === "APPROVED") : t.status === columnId);

  return (
    <>
      <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />
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
                  tasks={columnTasks(col.id)}
                  members={members}
                  onAssign={handleAssign}
                  onCardClick={(t: any) => setSelectedTaskForDetail(t)}
                  isPM={isPM}
                  onApprove={handleApprove}
                  onReject={(t: any) => setRejectTarget(t)}
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
          onUpdated={(updated: any) => {
            setTasks((prev) => prev.map((t) => t.id === updated.id ? { ...t, ...updated } : t));
            onTaskChange?.(updated.id, updated);
          }}
        />
      )}

      {/* 반려 사유 입력 모달 */}
      {rejectTarget && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <XCircle className="w-5 h-5" /> 업무 반려
              </h3>
              <button onClick={() => setRejectTarget(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              <span className="font-semibold text-foreground">"{rejectTarget.task_title}"</span> 업무를 반려합니다.
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
