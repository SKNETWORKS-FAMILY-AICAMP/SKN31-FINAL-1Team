"use client";

import { useState } from "react";
import { X, Loader2, Save, AlignLeft, BarChart2, CalendarClock, Lock, AlertTriangle } from "lucide-react";
import { isTaskOverdue } from "@/lib/taskOverdue";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import { Toast } from "@/components/ui/Toast";

const toDateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

// backend/tasks/models.py TaskStatusCode 실제 값 — status_info.code_name이 항상 우선이고,
// 이 맵은 status_info가 아직 없을 때(예: 낙관적 업데이트 직후)의 fallback 문구일 뿐이다.
const STATUS_LABEL: Record<string, string> = {
  PENDING_APPROVAL: "배분승인대기", TASK_APPROVED: "승인됨", IN_PROGRESS: "진행 중", DONE: "완료", CANCELLED: "취소됨",
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
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || "");
  const [progress, setProgress] = useState(task.progress || 0);
  const [assigneeId, setAssigneeId] = useState(task.assigned_user ? String(task.assigned_user) : "");
  // 일정 조율은 다른 화면(프로젝트 WBS 뷰)과 동일하게 PM 권한으로 취급한다.
  const [startDate, setStartDate] = useState(toDateInput(task.start_date));
  const [dueDate, setDueDate] = useState(toDateInput(task.end_date));

  const [isLoading, setIsLoading] = useState(false);
  const [isReopening, setIsReopening] = useState(false);
  const [errorToast, setErrorToast] = useState<string | null>(null);
  const overdue = isTaskOverdue({ wbsEnd: task.end_date, status: task.status_code });
  // PM 개별 승인 전(배분승인대기)에는 아직 실제로 착수한 업무가 아니므로 진행도를 매길 수 없다.
  const progressLocked = task.status_code === "PENDING_APPROVAL";
  // 2026-09-16: documents/page.tsx의 확정 업무 목록과 같은 이유 — 담당자가 배정을 승인했거나
  // (TASK_APPROVED) 이미 착수했거나(IN_PROGRESS) 완료(DONE)된 업무는 중간에 담당자만
  // 바꿔치기하면 안 된다. 단, 현재 담당자가 퇴사 처리됐으면 그 업무가 영영 재배정 못 하고
  // 방치되므로 상태와 무관하게 잠금을 풀어준다.
  const reassignLocked = ["TASK_APPROVED", "IN_PROGRESS", "DONE"].includes(task.status_code) && !task.assigned_user_resigned;

  const handleSave = async () => {
    setIsLoading(true);
    try {
      const updated = await apiFetch<any>(`/api/tasks/assignments/${task.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          title,
          description,
          // 진행률은 담당자 본인이 갱신하는 게 자연스러워 PM 제한 없이 저장하지만,
          // 배분승인대기 상태에서는 슬라이더 자체가 잠겨 있어 원래 값 그대로 보낸다.
          progress: progressLocked ? task.progress || 0 : progress,
          ...(isPM ? {
            assigned_user: assigneeId || null,
            start_date: startDate || null,
            end_date: dueDate || null,
          } : {}),
        }),
      });
      onUpdated?.(updated);
      onClose();
    } catch (err: any) {
      setErrorToast(err.message || "저장 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  // 2026-09-16: CANCELLED(반려)된 업무를 되돌릴 화면 경로가 없었다(사용자 리포트) —
  // 목록 화면의 "재승인 요청" 버튼과 같은 동작. 여기는 상세 모달이라 전용 상태변경
  // 엔드포인트(/status/)를 직접 호출한다(handleSave가 쓰는 일반 PATCH는 status_code를
  // 안 보낸다). 배분승인대기로 되돌려 PM이 승인/반려를 다시 판단하게 한다.
  const handleReopen = async () => {
    setIsReopening(true);
    try {
      const updated = await apiFetch<any>(`/api/tasks/assignments/${task.id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: "PENDING_APPROVAL" }),
      });
      onUpdated?.(updated.task ?? updated);
      onClose();
    } catch (err: any) {
      setErrorToast(err.message || "재승인 요청 중 오류가 발생했습니다.");
    } finally {
      setIsReopening(false);
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
              상태: <span className="font-semibold">{task.status_info?.code_name ?? STATUS_LABEL[task.status_code] ?? task.status_code}</span>
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
              {isPM && reassignLocked && <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground/70"><Lock className="w-3 h-3" /> 승인/착수된 업무는 담당자를 바꿀 수 없습니다</span>}
              {isPM && task.assigned_user_resigned && <span className="flex items-center gap-1 text-[11px] font-normal text-amber-500">담당자가 퇴사 처리되어 재배정이 필요합니다</span>}
            </label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              disabled={!isPM || reassignLocked}
              className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60"
            >
              <option value="">담당자 없음</option>
              {members.map((m: any) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            {/* 2026-09-16 (사용자 요청): 재배정하면 원래 AI가 누굴 추천했었는지 화면에서
                알 수 없어진다는 지적 — 현재 선택이 AI 원래 추천과 다를 때만 참고용으로 보여준다. */}
            {task.original_assigned_user_name && String(task.original_assigned_user) !== assigneeId && (
              <p className="text-[11px] text-muted-foreground">AI 추천 담당자: {task.original_assigned_user_name}</p>
            )}
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
              {progressLocked && (
                <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground/70"><Lock className="w-3 h-3" /> 배분 승인 후 설정할 수 있습니다</span>
              )}
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={progress}
              onChange={(e) => setProgress(Number(e.target.value))}
              disabled={progressLocked}
              className="w-full accent-primary disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <div className="w-full h-2 bg-black/5 dark:bg-white/5 rounded-full overflow-hidden mt-2">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>

          {task.status_code === "CANCELLED" && (
            <div className="p-3 rounded-lg bg-red-500/10 text-red-400 text-sm space-y-2">
              {task.reject_reason && <div>반려 사유: {task.reject_reason}</div>}
              {/* 2026-09-16 (다시 수정): 승인/반려가 담당자 권한이 되면서, 담당자가 반려하면
                  그 반려 응답을 받는 쪽은 PM이다 — "재승인 요청"은 PM이 다시 검토 대상으로
                  되돌리는 액션이라 PM 전용으로 되돌린다. 담당자 본인은 배지만 본다. */}
              {isPM && (
                <button
                  onClick={handleReopen}
                  disabled={isReopening}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-sky-500/10 text-sky-500 hover:bg-sky-500/20 transition-colors disabled:opacity-50"
                >
                  {isReopening ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                  재승인 요청 (배분승인대기로 되돌리기)
                </button>
              )}
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
      <Toast message={errorToast} variant="error" onDismiss={() => setErrorToast(null)} />
    </div>
  );
}
