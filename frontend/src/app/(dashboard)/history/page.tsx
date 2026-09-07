"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  History as HistoryIcon, FileText, ListTodo, Loader2, CheckCircle2,
  Clock, FolderKanban, PlusCircle, ChevronLeft, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api/client";

// 2026-09-02: 이 페이지는 원래 문서/업무의 "현재 상태"를 역추적해 이력을 재구성했었다(회의록/
// 기획서/요구사항정의서 각각에 별도 이벤트 로그가 없다는 전제로). 그런데 백엔드엔 이 화면을
// 위해 정확히 설계된 PipelineHistory 테이블 + /api/projects/{id}/history/ 가 이미 있어서
// (projects/serializers.py 주석: "/history 페이지 타임라인 및 로그 조회용 Serializer"),
// 굳이 재구성할 필요 없이 그 로그를 그대로 보여주면 된다 — 훨씬 정확하고 간단하다.
// 주의: 지금은 tasks/views.py의 업무 자동배정(TASK_ASSIGNED) 시점만 실제로 로그를 남기고
// 있어서, 회의록 등록/기획서 검토/요구사항 확정 단계는 아직 이 타임라인에 나타나지 않는다
// (백엔드에 로그 생성 코드 추가가 필요한 별도 작업).

type ProjectDto = { id: number; name: string };

type HistoryItem = {
  id: number;
  step_type: string;
  step_type_display: string;
  title: string;
  description: string | null;
  actor_info: { id: string; name: string } | null;
  created_at: string;
};

const STEP_META: Record<string, { icon: any; className: string }> = {
  MEETING_REGISTERED: { icon: FileText, className: "bg-blue-500/10 text-blue-500" },
  SPEC_GENERATED: { icon: FileText, className: "bg-violet-500/10 text-violet-500" },
  REQ_DEFINED: { icon: FileText, className: "bg-violet-500/10 text-violet-500" },
  TASK_ASSIGNED: { icon: ListTodo, className: "bg-teal-500/10 text-teal-500" },
  TASK_IN_PROGRESS: { icon: FolderKanban, className: "bg-primary/10 text-primary" },
  COMPLETED: { icon: CheckCircle2, className: "bg-emerald-500/10 text-emerald-500" },
};
const DEFAULT_STEP_META = { icon: HistoryIcon, className: "bg-muted text-muted-foreground" };

const PAGE_SIZE = 15;

export default function HistoryPage() {
  const [project, setProject] = useState<ProjectDto | null>(null);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // 단일 프로젝트 운영 전제 — 목록의 첫 프로젝트를 그대로 쓴다(다른 화면들과 동일한 패턴).
        const projects = await apiFetch<ProjectDto[]>("/api/projects/");
        const current = projects[0] ?? null;
        setProject(current);
        if (current) {
          const history = await apiFetch<HistoryItem[]>(`/api/projects/${current.id}/history/`);
          setItems(history);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  useEffect(() => { setPage(p => Math.min(p, totalPages)); }, [totalPages]);
  const pagedItems = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const relativeTime = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "방금 전";
    if (mins < 60) return `${mins}분 전`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}시간 전`;
    return `${Math.floor(hrs / 24)}일 전`;
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <FolderKanban className="w-10 h-10 text-muted-foreground/30" />
        <p className="text-muted-foreground">아직 프로젝트가 없습니다.</p>
        <Link href="/project/new" className="inline-flex items-center gap-1.5 mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold hover:bg-primary/90 transition-colors">
          <PlusCircle className="w-4 h-4" /> 첫 프로젝트 만들기
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          회의록 등록부터 기획서·요구사항정의서 검토, 업무 배정까지 전체 파이프라인 이력입니다.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="glass rounded-2xl border border-border p-16 text-center">
          <HistoryIcon className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
          <p className="text-muted-foreground text-sm">아직 이력이 없습니다.</p>
        </div>
      ) : (
        <div className="glass rounded-2xl border border-border divide-y divide-border overflow-hidden">
          {pagedItems.map(item => {
            const meta = STEP_META[item.step_type] ?? DEFAULT_STEP_META;
            const Icon = meta.icon;
            return (
              <div key={item.id} className="flex items-start gap-4 p-4">
                <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5", meta.className)}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm">{item.title}</span>
                    <span className="text-[11px] text-muted-foreground shrink-0">· {item.step_type_display}</span>
                  </div>
                  {item.description && (
                    <p className="text-xs text-muted-foreground mt-1">{item.description}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {item.actor_info && (
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {item.actor_info.name}
                    </span>
                  )}
                  <span className="text-[11px] text-muted-foreground">{relativeTime(item.created_at)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1.5">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(n => (
            <button
              key={n}
              onClick={() => setPage(n)}
              className={cn(
                "w-8 h-8 rounded-lg text-sm font-bold transition-colors",
                n === page ? "bg-primary text-primary-foreground" : "bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-muted-foreground"
              )}
            >
              {n}
            </button>
          ))}
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
