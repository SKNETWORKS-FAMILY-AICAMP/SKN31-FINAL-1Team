"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/lib/utils";

const WINDOW_SIZE = 10;

// 페이지가 많아지면(20~30페이지) 번호를 전부 한 줄에 나열하는 게 오히려 못 찾기
// 쉬워진다는 사용자 지적 — 10개 단위로 묶어서 보여주고, 구간을 넘어갈 때는
// 처음(<<)/끝(>>)으로 바로 이동하거나, 이전(<)/다음(>)으로 한 페이지씩 넘기다가
// 자연스럽게 다음 10개 구간으로 넘어가게 한다(업무관리/히스토리 공통 사용).
export function Pagination({
  page, totalPages, onChange,
}: {
  page: number; totalPages: number; onChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  const windowStart = Math.floor((page - 1) / WINDOW_SIZE) * WINDOW_SIZE + 1;
  const windowEnd = Math.min(windowStart + WINDOW_SIZE - 1, totalPages);
  const pages = Array.from({ length: windowEnd - windowStart + 1 }, (_, i) => windowStart + i);

  const navBtn = "p-2 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors";

  return (
    <div className="flex items-center justify-center gap-1.5 py-4">
      <button onClick={() => onChange(1)} disabled={page === 1} className={navBtn} title="맨 처음">
        <ChevronsLeft className="w-4 h-4" />
      </button>
      <button onClick={() => onChange(Math.max(1, page - 1))} disabled={page === 1} className={navBtn} title="이전 페이지">
        <ChevronLeft className="w-4 h-4" />
      </button>
      {pages.map(n => (
        <button
          key={n}
          onClick={() => onChange(n)}
          className={cn(
            "w-8 h-8 rounded-lg text-sm font-bold transition-colors",
            n === page ? "bg-primary text-primary-foreground" : "bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-muted-foreground"
          )}
        >
          {n}
        </button>
      ))}
      <button onClick={() => onChange(Math.min(totalPages, page + 1))} disabled={page === totalPages} className={navBtn} title="다음 페이지">
        <ChevronRight className="w-4 h-4" />
      </button>
      <button onClick={() => onChange(totalPages)} disabled={page === totalPages} className={navBtn} title="맨 끝">
        <ChevronsRight className="w-4 h-4" />
      </button>
    </div>
  );
}
