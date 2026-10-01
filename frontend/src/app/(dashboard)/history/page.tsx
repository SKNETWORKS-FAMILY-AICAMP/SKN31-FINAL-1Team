"use client";

import { useEffect, useMemo, useState } from "react";
import {
  History as HistoryIcon, FileText, Loader2, CheckCircle2,
  Clock, FolderKanban, Bot, AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { Pagination } from "@/components/ui/Pagination";

// 이 페이지는 백엔드의 PipelineHistory 테이블(/api/projects/{id}/history/)을 그대로
// 보여준다 — 문서/업무의 "현재 상태"를 프론트에서 역추적하지 않는다.

type ProjectDto = { id: number; name: string };

type HistoryItem = {
  id: number;
  project_name: string | null;
  step_type: string;
  step_type_display: string;
  title: string;
  description: string | null;
  actor_info: { id: string; name: string } | null;
  created_at: string;
};

const STEP_META: Record<string, { icon: any; className: string }> = {
  MEETING_REGISTERED: { icon: FileText, className: "bg-blue-500/10 text-blue-500" },
  SPEC_AI_GENERATED: { icon: Bot, className: "bg-teal-500/10 text-teal-500" },
  SPEC_GENERATED: { icon: FileText, className: "bg-violet-500/10 text-violet-500" },
  REQ_AI_GENERATED: { icon: Bot, className: "bg-teal-500/10 text-teal-500" },
  REQ_DEFINED: { icon: FileText, className: "bg-violet-500/10 text-violet-500" },
  TASK_AI_SUGGESTED: { icon: Bot, className: "bg-teal-500/10 text-teal-500" },
  TASK_ASSIGNED: { icon: Bot, className: "bg-teal-500/10 text-teal-500" },
  TASK_IN_PROGRESS: { icon: FolderKanban, className: "bg-primary/10 text-primary" },
  COMPLETED: { icon: CheckCircle2, className: "bg-emerald-500/10 text-emerald-500" },
};
const DEFAULT_STEP_META = { icon: HistoryIcon, className: "bg-muted text-muted-foreground" };

// heyzzabi2의 히스토리 필터를 참고 — "문서"(회의록/기획서/요구사항정의서)와 "업무"(배정/진행/완료)로
// 나누고, 그중 AI가 직접 실행한 이벤트만 "에이전트"로 따로 뽑아본다.
// 백엔드는 "AI 생성 버튼 클릭" 시점(SPEC_AI_GENERATED/REQ_AI_GENERATED/TASK_AI_SUGGESTED)과
// "사람이 검토·승인/확정한" 시점(SPEC_GENERATED/REQ_DEFINED/TASK_ASSIGNED)을 서로 다른
// step_type으로 남긴다 — 같은 값을 재사용하면 사람이 누른 승인까지 에이전트 탭에 섞이기
// 때문. AI 생성 이벤트는 "문서/업무 파이프라인의 한 단계"이면서 동시에 "AI가 한 일"이므로
// heyzzabi2와 같은 방식으로 문서·업무 탭과 에이전트 탭에 의도적으로 중복 노출한다.
const DOCUMENT_STEPS = new Set(["MEETING_REGISTERED", "SPEC_AI_GENERATED", "SPEC_GENERATED", "REQ_AI_GENERATED", "REQ_DEFINED"]);
const TASK_STEPS = new Set(["TASK_AI_SUGGESTED", "TASK_ASSIGNED", "TASK_IN_PROGRESS", "COMPLETED"]);
const AGENT_STEPS = new Set(["SPEC_AI_GENERATED", "REQ_AI_GENERATED", "TASK_AI_SUGGESTED", "TASK_ASSIGNED"]);

type FilterKey = "all" | "document" | "task" | "agent";
const FILTER_TABS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "document", label: "문서" },
  { key: "task", label: "업무" },
  { key: "agent", label: "에이전트" },
];

const PAGE_SIZE = 15;

export default function HistoryPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  // 조회 실패 시 projects가 빈 배열로 남는 건 "프로젝트가 없는 것"과 똑같이 보여서
  // (아래 projects.length === 0 분기), 네트워크 오류를 "아직 참여 중인 프로젝트가 없다"는
  // 오해를 주는 문구로 잘못 표시하는 문제가 있었다 — 실패 여부를 따로 들고 구분해서 보여준다.
  const [loadError, setLoadError] = useState(false);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [page, setPage] = useState(1);
  // null = "전체 보기" — 특정 프로젝트를 고르면 그 프로젝트 이력만 남긴다(사용자 요청,
  // 업무관리 페이지의 프로젝트 필터 드롭다운과 동일한 패턴).
  const [projectFilter, setProjectFilter] = useState<string | null>(null);

  // 마운트 시 한 번만 불러오고 끝이라, 히스토리 탭을 열어둔 채로 다른 화면(승인/배분 등)에서
  // 새 이력이 쌓여도 여기 화면엔 반영이 안 되는 문제가 있었다(실제 사용자 리포트). 탭을
  // 벗어났다 돌아오는(다른 창 보다가, 또는 다른 화면 갔다 옴) 흐름에서 최소한의 부담으로
  // 최신 상태를 다시 받아오도록, 마운트 시뿐 아니라 창이 다시 포커스될 때도 재조회한다.
  // projectFilter가 바뀌면 그 프로젝트(또는 전체)로 다시 불러온다.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setLoadError(false);
      try {
        const projectList = await apiFetch<ProjectDto[]>("/api/projects/");
        if (cancelled) return;
        setProjects(projectList);
        const historyUrl = projectFilter ? `/api/projects/${projectFilter}/history/` : "/api/projects/history/";
        const history = await apiFetch<HistoryItem[]>(historyUrl);
        if (cancelled) return;
        setItems(history);
      } catch (e) {
        if (cancelled) return;
        console.error(e);
        setLoadError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, [projectFilter]);

  // PM은 전체를 보고, 일반유저는 본인이 실행한 이력만 본다(사용자 요청, heyzzabi2 참고).
  // actor_info가 없는(작성자 정보 유실) 이력은 PM에게만 노출 — 일반유저 화면에서 "누가 한
  // 건지도 모르는데 내 것처럼 섞여 보이는" 걸 막는다.
  const visibleItems = useMemo(
    // actor_info.id가 타입 선언과 달리 실제로는 숫자로 내려온다(실측 확인) — user.id(문자열)와
    // 엄격 비교하면 항상 false가 되므로 양쪽을 문자열로 맞춰서 비교한다.
    () => isPM ? items : items.filter(i => i.actor_info && String(i.actor_info.id) === String(user?.id)),
    [items, isPM, user?.id]
  );

  const filteredItems = useMemo(() => visibleItems.filter(i => {
    if (filter === "all") return true;
    if (filter === "document") return DOCUMENT_STEPS.has(i.step_type);
    if (filter === "task") return TASK_STEPS.has(i.step_type);
    return AGENT_STEPS.has(i.step_type); // "agent"
  }), [visibleItems, filter]);

  // 필터가 바뀌면 목록이 통째로 달라지므로 페이지를 1로 되돌린다
  useEffect(() => { setPage(1); }, [filter, projectFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
  useEffect(() => { setPage(p => Math.min(p, totalPages)); }, [totalPages]);
  const pagedItems = filteredItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

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

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <AlertTriangle className="w-10 h-10 text-red-500/50" />
        <p className="text-muted-foreground">이력을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</p>
      </div>
    );
  }

  if (projects.length === 0) {
    // 2026-09-21 (사용자 요청): 히스토리는 조회 전용 화면이라 여기서 프로젝트를
    // "만들 수 있게" 유도할 필요가 없다 — 이력이 없다는 것만 보여준다(프로젝트
    // 생성 진입점은 대시보드/문서생성에만 둔다).
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <HistoryIcon className="w-10 h-10 text-muted-foreground/30" />
        <p className="text-muted-foreground">히스토리에 데이터가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div>
        {/* heyzzabi2엔 프로젝트명 제목이 없고, 이 앱도 다른 화면들(문서/업무/승인함/PDF/PPTX)에서
            이미 프로젝트명 배지를 일부러 뺐던 것과 통일 — 단일 프로젝트 전제라 굳이 강조 안 함. */}
        <p className="text-muted-foreground text-sm">
          {isPM
            ? "회의록 등록부터 기획서·요구사항정의서 검토, 업무 배정까지 전체 파이프라인 이력입니다."
            : "회의록 등록부터 기획서·요구사항정의서 검토, 업무 배정까지 내가 실행한 이력입니다."}
        </p>
      </div>

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-1 p-1 bg-black/5 dark:bg-white/5 rounded-xl w-fit">
          {FILTER_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-bold transition-all",
                filter === tab.key ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <select
          value={projectFilter ?? ""}
          onChange={e => setProjectFilter(e.target.value || null)}
          className="px-4 py-2.5 bg-card border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded-xl text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40 focus:bg-background transition-all shadow-sm"
        >
          <option value="">전체 보기</option>
          {projects.map(p => (
            <option key={p.id} value={String(p.id)}>{p.name}</option>
          ))}
        </select>
      </div>

      {filteredItems.length === 0 ? (
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
                  {/* 2026-09-22 (사용자 요청): "전체 보기"로 여러 프로젝트 이력이 섞여 보일 때
                      항목마다 어느 프로젝트인지 바로 구분되어야 함 — 업무관리 칸반 카드와
                      동일한 스타일(파란색, 제목 위)로 표시. */}
                  {item.project_name && (
                    <div className="text-[11px] font-bold text-primary mb-0.5">{item.project_name}</div>
                  )}
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

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
