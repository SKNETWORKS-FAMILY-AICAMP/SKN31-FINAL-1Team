"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { apiFetch } from "@/lib/api/client";

type Job = { id: string; status: "PENDING" | "RUNNING" | "SUCCESS" | "ERROR"; stage: string; message: string };

export function FullAutoPanel({ noteId, canView, onCompleted, children }: {
  noteId: number; canView: boolean; onCompleted: () => Promise<void>; children: ReactNode;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(canView);
  const [retrying, setRetrying] = useState(false);
  const [revision, setRevision] = useState(0);
  const completed = useRef(onCompleted);
  useEffect(() => { completed.current = onCompleted; }, [onCompleted]);

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await apiFetch<{ job: Job | null }>(`/api/meetings/notes/${noteId}/full-auto/`);
        if (cancelled) return;
        setJob(response.job);
        setChecking(false);
        setError("");
        if (response.job?.status === "SUCCESS") {
          await completed.current();
        } else if (response.job && ["PENDING", "RUNNING"].includes(response.job.status)) {
          timer = setTimeout(poll, 2500);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "자동 실행 상태를 확인하지 못했습니다.");
        timer = setTimeout(poll, 5000);
      }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [noteId, canView, revision]);

  async function retry() {
    setRetrying(true);
    try {
      await apiFetch(`/api/meetings/notes/${noteId}/full-auto/`, { method: "POST" });
      setJob(previous => previous ? { ...previous, status: "PENDING", stage: "재시도 대기", message: "" } : null);
      setRevision(value => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "재시도 요청 실패");
    } finally { setRetrying(false); }
  }

  return <>
    {canView && !checking && !job && !error && <button type="button" disabled={retrying} onClick={retry} className="mb-4 rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">
      {retrying ? "요청 중…" : "이 회의록으로 자동 업무 배분 시작"}
    </button>}
    {(job || error || checking) && <div role="status" aria-live="polite" className="mb-5 rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
      <strong>자동 업무 배분</strong>
      <p>{checking ? "진행 상태 확인 중…" : job?.stage}</p>
      {job?.status === "PENDING" && <p className="text-muted-foreground">자동 실행을 기다리고 있습니다.</p>}
      {job?.status === "ERROR" && <p className="text-red-500">{job.message}</p>}
      {error && <p className="text-red-500">{error}</p>}
      {canView && job?.status === "ERROR" && <button type="button" disabled={retrying} onClick={retry} className="mt-2 rounded bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50">{retrying ? "요청 중…" : "실패한 단계부터 재시도"}</button>}
    </div>}
    <fieldset disabled={checking || (!!job && job.status !== "SUCCESS")} className="min-w-0 disabled:opacity-70">
      {children}
    </fieldset>
  </>;
}
