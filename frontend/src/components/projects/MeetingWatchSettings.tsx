"use client";

import { useEffect, useState } from "react";
import { FolderSearch, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api/client";

type WatchStatus = {
  enabled: boolean;
  running: boolean;
  project_id: number | null;
  folder: string;
  folder_available: boolean;
  last_error: string;
  heartbeat_at: string | null;
};
type Project = { id: number; name: string };

export function MeetingWatchSettings() {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | "">("");
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const refresh = () => apiFetch<WatchStatus>("/api/meetings/watch-control/")
      .then(data => { if (active) { setStatus(data); if (data.project_id) setProjectId(data.project_id); setFolder(current => current || data.folder || ""); } })
      .catch(err => { if (active) setError(err.message || "감시 상태를 조회하지 못했습니다."); });
    refresh();
    apiFetch<Project[]>("/api/projects/")
      .then(data => { if (active) setProjects(data); })
      .catch(() => {});
    const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const saveFolder = async () => {
    if (busy || status?.enabled) return;
    setBusy(true);
    setError("");
    try {
      const updated = await apiFetch<WatchStatus>("/api/meetings/watch-control/", {
        method: "PATCH",
        body: JSON.stringify({ folder }),
      });
      setStatus(updated);
      setFolder(updated.folder);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "폴더를 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async () => {
    if (!status || busy) return;
    setError("");
    setBusy(true);
    try {
      const next = !status.enabled;
      const updated = await apiFetch<WatchStatus>("/api/meetings/watch-control/", {
        method: "POST",
        body: JSON.stringify({ enabled: next, project_id: next ? projectId : undefined, folder: next ? folder : undefined }),
      });
      setStatus(updated);
      setFolder(updated.folder || folder);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "감시 설정을 변경하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass rounded-2xl border border-border p-6 space-y-4">
      <div className="flex items-center gap-2">
        <FolderSearch className="w-5 h-5 text-primary" />
        <h2 className="text-lg font-bold">회의록 폴더 자동 감시</h2>
      </div>
      <p className="text-sm text-muted-foreground">날짜별 폴더에 회의록이 추가되면 통합 요약부터 업무배분까지 자동 실행합니다. 새 요약본은 선택한 프로젝트에 등록됩니다.</p>
      <label className="block space-y-1 text-sm font-medium">
        <span>내 회의록 폴더 경로</span>
        <input className="w-full rounded-lg border border-border bg-background px-3 py-2"
          value={folder} onChange={e => setFolder(e.target.value)} disabled={busy || !!status?.enabled}
          placeholder="예: C:\\Users\\Playdata\\Desktop\\회의록\\홍길동" />
        <span className="block text-xs text-muted-foreground">이 폴더 아래에 YYYYMMDD 날짜 폴더를 만들어 회의록을 넣으세요. 백엔드가 접근할 수 있는 경로여야 합니다.</span>
      </label>
      <button type="button" onClick={saveFolder} disabled={busy || !!status?.enabled || !folder.trim()}
        className="rounded-lg border border-border px-3 py-2 text-sm font-semibold disabled:opacity-50">
        감시 폴더 저장
      </button>
      <label className="block space-y-1 text-sm font-medium">
        <span>결과를 등록할 프로젝트</span>
        <select className="w-full rounded-lg border border-border bg-background px-3 py-2" value={projectId}
          onChange={e => setProjectId(e.target.value ? Number(e.target.value) : "")}
          disabled={busy || !!status?.enabled}>
          <option value="">프로젝트 선택</option>
          {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm">
          <div className="font-semibold">{status?.enabled ? (status.running ? "감시 중" : "감시 시작 중") : "감시 꺼짐"}</div>
          <div className="text-xs text-muted-foreground">OFF 후 진행 중인 AI 작업은 완료될 때까지 계속됩니다.</div>
        </div>
        <button type="button" role="switch" aria-checked={!!status?.enabled} aria-label="회의록 폴더 감시"
          onClick={toggle} disabled={!status || busy || (!status.enabled && (!projectId || !folder.trim() || !status.folder_available))}
          className={`relative h-8 w-14 shrink-0 rounded-full transition-colors disabled:opacity-50 ${status?.enabled ? "bg-primary" : "bg-muted"}`}>
          <span className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow transition-transform ${status?.enabled ? "translate-x-1" : "-translate-x-5"}`} />
          {busy && <Loader2 className="absolute -right-6 top-1.5 h-4 w-4 animate-spin" />}
        </button>
      </div>
      {!status?.folder_available && <p className="text-sm text-amber-600">백엔드의 허용 경로가 설정되지 않았습니다.</p>}
      {(error || status?.last_error) && <p role="alert" className="text-sm text-red-600">{error || status?.last_error}</p>}
    </section>
  );
}
