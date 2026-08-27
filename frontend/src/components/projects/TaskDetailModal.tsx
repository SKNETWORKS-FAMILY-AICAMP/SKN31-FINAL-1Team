"use client";

import { useState, useEffect } from "react";
import { X, Loader2, Save, AlignLeft, BarChart2, CalendarClock, Lock, AlertTriangle } from "lucide-react";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const toDateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

// 다른 화면(업무관리 등)과 같은 한글 라벨로 통일 — 이 모달만 status 원문(IN_PROGRESS 등)을 그대로 보여주고 있었다.
const STATUS_LABEL: Record<string, string> = {
  BACKLOG: "대기", PENDING_APPROVAL: "배분승인대기", IN_PROGRESS: "진행 중", DONE: "완료", CANCELLED: "취소됨",
};

export function TaskDetailModal({
  task,
  members,
  onClose,
}: {
  task: any;
  members: any[];
  onClose: () => void;
}) {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || "");
  const [progress, setProgress] = useState(task.progress || 0);
  const [assigneeId, setAssigneeId] = useState(task.assigneeId || "");
  const [status, setStatus] = useState(task.status);
  // FR: 실제 진행 상황이 AI가 처음 잡은 예상 소요시간/일정과 어긋나도 고칠 방법이 없었다 —
  // 일정 조율은 다른 화면(프로젝트 WBS 뷰)과 동일하게 PM 권한으로 취급한다.
  const [wbsStart, setWbsStart] = useState(toDateInput(task.wbsStart));
  const [wbsEnd, setWbsEnd] = useState(toDateInput(task.wbsEnd));
  const [estimatedHours, setEstimatedHours] = useState(task.estimatedHours ?? "");

  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const handleSave = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`/api/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          description,
          progress,
          assigneeId,
          status,
          ...(isPM ? {
            wbsStart: wbsStart || null,
            wbsEnd: wbsEnd || null,
            estimatedHours: estimatedHours === "" ? null : Number(estimatedHours),
          } : {}),
        }),
      });

      if (!res.ok) throw new Error("저장 실패");

      router.refresh();
      onClose();
    } catch (error) {
      console.error(error);
      alert("저장 중 오류가 발생했습니다.");
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
              업무가 속한 상태: <span className="font-semibold">{STATUS_LABEL[status] ?? status}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 flex-1 overflow-y-auto space-y-8">
          
          <div className="space-y-3">
            <label className="text-sm font-semibold text-muted-foreground">담당자</label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="">담당자 없음</option>
              {members.map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              <CalendarClock className="w-4 h-4" /> 일정 · 예상 소요시간
              {!isPM && <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground/70"><Lock className="w-3 h-3" /> 재계획은 PM만 할 수 있습니다</span>}
              {isTaskOverdue(task) && (
                <span className="flex items-center gap-1 text-[11px] font-bold text-red-500 ml-auto">
                  <AlertTriangle className="w-3.5 h-3.5" /> 마감일이 지났습니다
                </span>
              )}
            </label>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">시작일</label>
                <input
                  type="date"
                  value={wbsStart}
                  onChange={(e) => setWbsStart(e.target.value)}
                  readOnly={!isPM}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
                  disabled={!isPM}
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">종료일</label>
                <input
                  type="date"
                  value={wbsEnd}
                  onChange={(e) => setWbsEnd(e.target.value)}
                  readOnly={!isPM}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
                  disabled={!isPM}
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">예상 소요시간(h)</label>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={estimatedHours}
                  onChange={(e) => setEstimatedHours(e.target.value === "" ? "" : Number(e.target.value))}
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
