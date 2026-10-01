"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import {
  CheckCircle2, XCircle, AlertCircle, Clock, Loader2,
  MessageSquare, RotateCcw, ShieldCheck
} from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { Toast } from "@/components/ui/Toast";

type Task = {
  id: number;
  title: string;
  status_code: string;
  description?: string | null;
  reject_reason?: string | null;
  progress: number;
  assigned_user_name: string | null;
  project: number | null;
  updated_at: string;
};

export default function ApprovalsPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [rejectModal, setRejectModal] = useState<{ id: number; title: string } | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [errorToast, setErrorToast] = useState<string | null>(null);

  useEffect(() => {
    const fetchTasks = async () => {
      setLoading(true);
      try {
        const url = isPM
          ? "/api/tasks/assignments/?status=PENDING_APPROVAL"
          : user?.id
          ? `/api/tasks/assignments/?assigneeId=${user.id}&status=PENDING_APPROVAL`
          : null;

        if (!url) return;

        const data = await apiFetch<Task[]>(url);
        setTasks(data);
      } catch (e: any) {
        setErrorToast(e.message || "승인 대기 목록을 불러오지 못했습니다.");
      } finally {
        setLoading(false);
      }
    };
    if (user) fetchTasks();
  }, [user, isPM]);

  const handleApprove = async (taskId: number) => {
    setProcessingId(taskId);
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: "TASK_APPROVED" }),
      });
      setTasks(prev => prev.filter(t => t.id !== taskId));
    } catch (e: any) {
      setErrorToast(e.message || "승인 처리에 실패했습니다.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async () => {
    if (!rejectModal || !rejectReason.trim()) return;
    setProcessingId(rejectModal.id);
    try {
      await apiFetch(`/api/tasks/assignments/${rejectModal.id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: "CANCELLED", reject_reason: rejectReason }),
      });
      setTasks(prev => prev.filter(t => t.id !== rejectModal.id));
      setRejectModal(null);
      setRejectReason("");
    } catch (e: any) {
      setErrorToast(e.message || "반려 처리에 실패했습니다.");
    } finally {
      setProcessingId(null);
    }
  };

  const relativeTime = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}분 전`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}시간 전`;
    return `${Math.floor(hrs / 24)}일 전`;
  };

  return (
    <div className="w-full max-w-5xl mx-auto space-y-8 animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <ShieldCheck className="w-8 h-8 text-orange-400" />
          {/* 2026-09-22 (사용자 재확인 — 9/16 정책으로 재복귀): 배분 승인/반려는 PM이
              검토하는 게 아니라, PM이 배정한 업무를 담당자 본인이 받아들일지 정하는
              것이다 — 그래서 액션(승인/반려)은 담당자 본인에게, PM에게는 팀 전체
              현황을 보여주는 읽기 전용 화면으로 뒤집는다. */}
          {isPM ? "팀 배분 요청 현황" : "내 배분 승인 대기함"}
        </h1>
        <p className="text-muted-foreground mt-1">
          {isPM
            ? "팀원에게 배정 요청한 업무들의 수락/반려 처리 현황입니다. (업무관리 칸반의 \"승인 대기\" 칼럼과 동일한 목록입니다)"
            : "나에게 배정 요청된 업무를 수락하거나 반려하세요."}
        </p>
      </div>

      {/* Summary pill */}
      {!loading && (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2 bg-orange-500/10 border border-orange-500/20 rounded-full text-sm font-semibold text-orange-400">
            <AlertCircle className="w-4 h-4" />
            {tasks.length > 0 ? `${tasks.length}건 검토 대기 중` : "대기 중인 요청이 없습니다"}
          </div>
        </div>
      )}

      {/* Task cards */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-muted-foreground text-sm">불러오는 중...</p>
        </div>
      ) : tasks.length === 0 ? (
        <div className="glass rounded-2xl border border-border p-16 text-center">
          <CheckCircle2 className="w-14 h-14 text-emerald-400 mx-auto mb-4" />
          <h3 className="text-xl font-bold mb-2">
            {isPM ? "대기 중인 배분 요청이 없습니다." : "아직 나에게 배분 요청된 업무가 없습니다."}
          </h3>
          <p className="text-muted-foreground text-sm">
            {isPM
              ? "팀원에게 업무를 배정하면 여기서 수락/반려 처리 현황을 볼 수 있습니다."
              : "PM이 업무를 배정하면 여기서 수락하거나 반려할 수 있습니다."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map(task => (
            <div
              key={task.id}
              className="glass rounded-2xl border border-orange-500/20 p-6 hover:border-orange-500/40 transition-all group"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Time */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-muted-foreground text-xs flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {relativeTime(task.updated_at)}
                    </span>
                  </div>

                  {/* Title */}
                  <h3 className="font-bold text-lg leading-tight mb-1">{task.title}</h3>

                  {/* Assignee (PM view) */}
                  {isPM && task.assigned_user_name && (
                    <div className="flex items-center gap-2 mt-2">
                      <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center text-xs font-bold text-primary">
                        {task.assigned_user_name.charAt(0)}
                      </div>
                      <span className="text-sm text-muted-foreground">{task.assigned_user_name}에게 배정 요청</span>
                    </div>
                  )}

                  {/* Progress */}
                  <div className="flex items-center gap-2 mt-3">
                    <div className="flex-1 h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden max-w-[160px]">
                      <div
                        className="h-full bg-orange-400 rounded-full"
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground">{task.progress}% 완료</span>
                  </div>
                </div>

                {/* 2026-09-22 (사용자 재확인 — 9/16 정책으로 재복귀): 수락/반려는 그
                    업무를 배정받은 담당자 본인 권한 — PM은 자기 팀 현황을 읽기 전용
                    배지로만 본다. */}
                {!isPM && (
                  <div className="flex flex-col gap-2 shrink-0">
                    <button
                      onClick={() => handleApprove(task.id)}
                      disabled={processingId === task.id}
                      className="flex items-center gap-2 px-4 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
                    >
                      {processingId === task.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4" />
                      )}
                      수락
                    </button>
                    <button
                      onClick={() => setRejectModal({ id: task.id, title: task.title })}
                      disabled={processingId === task.id}
                      className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      반려
                    </button>
                  </div>
                )}

                {/* Status (PM view) */}
                {isPM && (
                  <span className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-orange-400 bg-orange-400/10 border border-orange-400/20">
                    <AlertCircle className="w-3.5 h-3.5" />
                    담당자 수락 대기 중
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <h3 className="text-xl font-bold mb-1 flex items-center gap-2">
              <RotateCcw className="w-5 h-5 text-red-400" />
              반려 사유 입력
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              <span className="font-semibold text-foreground">"{rejectModal.title}"</span> 업무 배정을 반려합니다.
              PM에게 전달할 반려 사유를 입력해 주세요.
            </p>
            <div className="relative mb-4">
              <MessageSquare className="w-4 h-4 absolute left-3 top-3.5 text-muted-foreground" />
              <textarea
                className="w-full pl-9 pr-4 py-3 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 resize-none h-28"
                placeholder="예: 요구사항 명세서 보완이 필요합니다. 3번 항목 재검토 요청."
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => { setRejectModal(null); setRejectReason(""); }}
                className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleReject}
                disabled={processingId !== null || !rejectReason.trim()}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 text-sm font-semibold transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {processingId ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                반려 처리
              </button>
            </div>
          </div>
        </div>
      )}

      <Toast message={errorToast} variant="error" onDismiss={() => setErrorToast(null)} />
    </div>
  );
}