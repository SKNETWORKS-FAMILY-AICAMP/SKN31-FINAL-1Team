"use client";

import { useState } from "react";
import { X, Loader2, Save, AlignLeft, BarChart2, CalendarClock, Lock, AlertTriangle } from "lucide-react";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";

const toDateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

// Django TaskAssignment.Status 실제 값 — 예전 BACKLOG/DONE/CANCELLED는 없다.
const STATUS_LABEL: Record<string, string> = {
  PENDING_APPROVAL: "승인 대기", APPROVED: "승인됨", IN_PROGRESS: "진행 중", COMPLETED: "완료", REJECTED: "반려됨",
};

export function TaskDetailModal({
  task,
  members,
  onClose,
  onUpdated,
}: {
  task: any;
  members: any[];
  onClose: () => void;
  onUpdated?: (updated: any) => void;
}) {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [title, setTitle] = useState(task.task_title);
  const [description, setDescription] = useState(task.task_description || "");
  const [progress, setProgress] = useState(task.progress || 0);
  const [assigneeId, setAssigneeId] = useState(task.assigned_user ? String(task.assigned_user) : "");
  // 일정 조율은 다른 화면(프로젝트 WBS 뷰)과 동일하게 PM 권한으로 취급한다.
  const [startDate, setStartDate] = useState(toDateInput(task.start_date));
  const [dueDate, setDueDate] = useState(toDateInput(task.due_date));

  const [isLoading, setIsLoading] = useState(false);
  const overdue = isTaskOverdue({ wbsEnd: task.due_date, status: task.status });

  const handleSave = async () => {
    setIsLoading(true);
    try {
      const updated = await apiFetch<any>(`/api/tasks/assignments/${task.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          task_title: title,
          task_description: description,
          // 진행률은 담당자 본인이 갱신하는 게 자연스러워 PM 제한 없이 항상 저장
          progress,
          ...(isPM ? {
            assigned_user: assigneeId || null,
            start_date: startDate || null,
            due_date: dueDate || null,
          } : {}),
        }),
      });
      onUpdated?.(updated);
      onClose();
    } catch (err: any) {
      alert(err.message || "저장 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-2xl border border-border flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-start p-6 border-b border-border">
          <div className="w-full mr-4">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="text-2xl font-bold bg-transparent border-none outline-none w-full focus:ring-0 p-0 placeholder:text-muted-foreground/50"
              placeholder="업무 제목"
            />
            <div className="text-sm text-muted-foreground mt-1">
              {task.req_code && <span className="mr-2">{task.req_code}</span>}
              상태: <span className="font-semibold">{STATUS_LABEL[task.status] ?? task.status}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 flex-1 overflow-y-auto space-y-8">

          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              담당자
              {/* 재배정은 일정과 같은 이유로 PM 고유 권한 */}
              {!isPM && <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground/70"><Lock className="w-3 h-3" /> 재배정은 PM만 할 수 있습니다</span>}
            </label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              disabled={!isPM}
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
            >
              <option value="">담당자 없음</option>
              {members.map((m: any) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              <CalendarClock className="w-4 h-4" /> 일정
              {!isPM && <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground/70"><Lock className="w-3 h-3" /> 재계획은 PM만 할 수 있습니다</span>}
              {overdue && (
                <span className="flex items-center gap-1 text-[11px] font-bold text-red-500 ml-auto">
                  <AlertTriangle className="w-3.5 h-3.5" /> 마감일이 지났습니다
                </span>
              )}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">시작일</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  disabled={!isPM}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">마감일</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  disabled={!isPM}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
                />
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <BarChart2 className="w-4 h-4" /> 진행도 ({progress}%)
              </label>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={progress}
              onChange={(e) => setProgress(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="w-full h-2 bg-black/5 dark:bg-white/5 rounded-full overflow-hidden mt-2">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>

          {task.status === "REJECTED" && task.reject_reason && (
            <div className="p-3 rounded-lg bg-red-500/10 text-red-400 text-sm">
              반려 사유: {task.reject_reason}
            </div>
          )}

          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              <AlignLeft className="w-4 h-4" /> 상세 설명
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="업무에 대한 상세한 설명을 적어주세요..."
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 min-h-[150px] resize-none focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 p-6 border-t border-border bg-black/5 dark:bg-white/5">
          <button onClick={onClose} className="px-5 py-2 font-medium text-sm text-muted-foreground hover:bg-black/10 dark:hover:bg-white/10 rounded-lg transition-colors">
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={isLoading}
            className="flex items-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 px-8 py-2 rounded-lg transition-colors text-sm font-medium shadow-lg shadow-primary/20 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            변경사항 저장
          </button>
        </div>
      </div>
    </div>
  );
}
