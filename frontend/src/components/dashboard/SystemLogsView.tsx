"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api/client";

type LogResponse = { lines: string[]; truncated: boolean; available: boolean };
type Filter = "all" | "error" | "warning";

export default function SystemLogsView() {
  const [data, setData] = useState<LogResponse | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiFetch<LogResponse>("/api/dashboard/system-logs/"));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "시스템 로그를 가져오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiFetch<LogResponse>("/api/dashboard/system-logs/")
      .then(result => { if (active) setData(result); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : "시스템 로그를 가져오지 못했습니다."); });
    return () => { active = false; };
  }, []);

  const visible = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.lines;
    const signal = filter === "error" ? /\b(ERROR|CRITICAL)\b/i : /\bWARNING\b/i;
    const kept: string[] = [];
    let includeTraceback = false;
    for (const line of data.lines) {
      if (/^\[\d{4}-\d{2}-\d{2} /.test(line)) includeTraceback = signal.test(line);
      if (includeTraceback) kept.push(line);
    }
    return kept;
  }, [data, filter]);

  return (
    <section className="rounded-2xl border border-border bg-background p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">시스템 로그</h2>
          <p className="text-xs text-muted-foreground">백엔드 django.log의 최근 기록입니다. 문제 확인 후 작업 상태 화면에서 재시도하세요.</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-semibold disabled:opacity-50">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> 새로고침
        </button>
      </div>
      <div className="flex gap-2" role="group" aria-label="로그 수준 필터">
        {(["all", "error", "warning"] as const).map(value => (
          <button key={value} type="button" onClick={() => setFilter(value)}
            aria-pressed={filter === value}
            className={`rounded-lg px-3 py-1.5 text-sm ${filter === value ? "bg-primary text-primary-foreground" : "border border-border"}`}>
            {value === "all" ? "전체" : value === "error" ? "오류" : "경고"}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="flex items-center gap-2 text-sm text-red-600"><AlertCircle className="h-4 w-4" />{error}</p>}
      {data && !data.available && <p className="text-sm text-muted-foreground">아직 생성된 로그 파일이 없습니다.</p>}
      {data?.truncated && <p className="text-xs text-muted-foreground">최근 250줄 또는 128KB만 표시합니다.</p>}
      {data?.available && <pre className="max-h-[65vh] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-100 whitespace-pre-wrap break-all" aria-label="시스템 로그 내용">
        {visible.length ? visible.join("\n") : "표시할 기록이 없습니다."}
      </pre>}
    </section>
  );
}
