"use client";

import { useEffect, useMemo, useRef } from "react";
import { FileText, GripVertical, PanelRightClose, X } from "lucide-react";

type TextPart = { text: string; highlighted: boolean; quoteIndex?: number; groupIndex?: number };

export type EvidenceGroup = { title: string; quotes: string[] };

// 항목(예: 기능 5개)별로 색을 다르게 써서 "어느 하이라이트가 어느 항목 근거인지"
// 구분할 수 있게 한다 — 항목 정보가 없는 섹션(대상 사용자·기술 스택·최종 결정 등,
// 아직 항목별 근거가 안 쪼개진 섹션)은 이 팔레트를 쓰지 않고 기존 단색(amber) 그대로
// 유지한다. 그런 섹션은 targetGroups를 안 넘기면 되므로 동작이 하나도 안 바뀐다.
// border는 ProposalTemplate이 본문 쪽(왼쪽 패널) 항목에 같은 색 테두리를 매칭할 때
// 쓴다 — 근거 패널(mark/dot)과 본문(border) 양쪽이 같은 배열·같은 순서를 공유해야
// "몇 번째 항목이 무슨 색"이 항상 일치한다(두 파일에 팔레트를 따로 두지 않는 이유).
export const EVIDENCE_GROUP_PALETTE = [
  { mark: "bg-amber-200 ring-amber-300", dot: "bg-amber-500", border: "border-amber-500" },
  { mark: "bg-sky-200 ring-sky-300", dot: "bg-sky-500", border: "border-sky-500" },
  { mark: "bg-emerald-200 ring-emerald-300", dot: "bg-emerald-500", border: "border-emerald-500" },
  { mark: "bg-violet-200 ring-violet-300", dot: "bg-violet-500", border: "border-violet-500" },
  { mark: "bg-rose-200 ring-rose-300", dot: "bg-rose-500", border: "border-rose-500" },
  { mark: "bg-orange-200 ring-orange-300", dot: "bg-orange-500", border: "border-orange-500" },
  { mark: "bg-teal-200 ring-teal-300", dot: "bg-teal-500", border: "border-teal-500" },
  { mark: "bg-fuchsia-200 ring-fuchsia-300", dot: "bg-fuchsia-500", border: "border-fuchsia-500" },
] as const;

function buildHighlightedParts(
  fullText: string,
  targetQuotes: string[],
  groupOfQuote?: (quoteIndex: number) => number | undefined,
): TextPart[] {
  const matches = targetQuotes
    .map((quote, quoteIndex) => ({ quote: quote.trim(), quoteIndex }))
    .filter(({ quote }) => quote.length > 0)
    .flatMap(({ quote, quoteIndex }) => {
      const positions: { start: number; end: number; quoteIndex: number }[] = [];
      let from = 0;
      while (from < fullText.length) {
        const start = fullText.indexOf(quote, from);
        if (start === -1) break;
        positions.push({ start, end: start + quote.length, quoteIndex });
        from = start + quote.length;
      }
      return positions;
    })
    .sort((a, b) => a.start - b.start || b.end - a.end);

  if (matches.length === 0) return [{ text: fullText, highlighted: false }];

  const parts: TextPart[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.start < cursor) continue;
    if (match.start > cursor) parts.push({ text: fullText.slice(cursor, match.start), highlighted: false });
    parts.push({
      text: fullText.slice(match.start, match.end), highlighted: true, quoteIndex: match.quoteIndex,
      groupIndex: groupOfQuote?.(match.quoteIndex),
    });
    cursor = match.end;
  }
  if (cursor < fullText.length) parts.push({ text: fullText.slice(cursor), highlighted: false });
  return parts;
}

export function EvidencePanel({
  open, onClose, fullText, targetQuotes, targetGroups, width = 560, onWidthChange,
}: {
  open: boolean;
  onClose: () => void;
  fullText: string;
  targetQuotes: string[];
  // 항목별 근거가 준비된 섹션(현재는 주요 기능)에서만 넘어온다. 없으면(대부분의
  // 섹션) 기존처럼 targetQuotes를 단색으로 하이라이트한다 — 동작 변화 없음.
  targetGroups?: EvidenceGroup[];
  width?: number;
  onWidthChange?: (width: number) => void;
}) {
  const firstHighlightRef = useRef<HTMLElement>(null);
  const hasGroups = !!targetGroups && targetGroups.length > 0;

  const { quotes, groupOfQuote } = useMemo(() => {
    if (!hasGroups) return { quotes: targetQuotes, groupOfQuote: undefined as ((i: number) => number | undefined) | undefined };
    const flatQuotes: string[] = [];
    const groupIndexByQuoteIndex: number[] = [];
    targetGroups!.forEach((group, groupIndex) => {
      group.quotes.forEach(quote => {
        flatQuotes.push(quote);
        groupIndexByQuoteIndex.push(groupIndex);
      });
    });
    return { quotes: flatQuotes, groupOfQuote: (i: number) => groupIndexByQuoteIndex[i] };
  }, [hasGroups, targetGroups, targetQuotes]);

  const parts = useMemo(() => buildHighlightedParts(fullText, quotes, groupOfQuote), [fullText, quotes, groupOfQuote]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      firstHighlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, parts, onClose]);

  const resizeFromPointer = (clientX: number) => {
    const maxWidth = Math.min(720, window.innerWidth * 0.55);
    onWidthChange?.(Math.round(Math.min(maxWidth, Math.max(360, window.innerWidth - clientX))));
  };
  const startResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeFromPointer(event.clientX);
  };

  let assignedFirstRef = false;
  return (
    <div
      className={`pointer-events-none fixed inset-0 z-[120] print:hidden transition ${open ? "visible" : "invisible delay-300"}`}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label="원문 패널 닫기"
        tabIndex={open ? 0 : -1}
        onClick={onClose}
        className={`pointer-events-auto absolute inset-0 bg-slate-950/45 backdrop-blur-[1px] transition-opacity duration-300 xl:hidden ${open ? "opacity-100" : "opacity-0"}`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="회의록 원문"
        style={{ "--evidence-panel-width": `${width}px` } as React.CSSProperties}
        className={`pointer-events-auto absolute right-0 top-0 flex h-full w-full flex-col border-l border-border bg-background text-foreground shadow-2xl transition-transform duration-300 ease-out xl:w-[var(--evidence-panel-width)] xl:shadow-xl ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        <button
          type="button"
          role="separator"
          aria-label="원문 패널 너비 조절"
          aria-orientation="vertical"
          aria-valuemin={360}
          aria-valuemax={720}
          aria-valuenow={width}
          onPointerDown={startResize}
          onPointerMove={event => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeFromPointer(event.clientX);
          }}
          onKeyDown={event => {
            if (event.key === "ArrowLeft") onWidthChange?.(Math.min(720, width + 24));
            if (event.key === "ArrowRight") onWidthChange?.(Math.max(360, width - 24));
          }}
          className="absolute -left-3 top-1/2 z-10 hidden h-12 w-6 -translate-y-1/2 cursor-col-resize items-center justify-center rounded-md border border-border bg-background text-muted-foreground shadow-md hover:text-primary xl:flex"
        >
          <GripVertical className="h-4 w-4" />
        </button>
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-primary/10 p-2 text-primary"><FileText className="h-5 w-5" /></span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-bold">회의록 원문</h2>
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">근거 {quotes.length}개</span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {hasGroups ? "강조된 문장이 각 항목의 근거입니다. 색으로 항목을 구분합니다." : "강조된 문장이 해당 기능의 근거입니다."}
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10" aria-label="닫기">
            <PanelRightClose className="hidden h-5 w-5 xl:block" />
            <X className="h-5 w-5 xl:hidden" />
          </button>
        </header>
        {hasGroups && (
          <div className="flex flex-wrap gap-1.5 border-b border-border bg-black/[0.02] px-5 py-3 dark:bg-white/[0.02]">
            {targetGroups!.map((group, groupIndex) => (
              <span
                key={group.title + groupIndex}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-semibold text-foreground/80"
              >
                <span className={`h-2 w-2 rounded-sm ${EVIDENCE_GROUP_PALETTE[groupIndex % EVIDENCE_GROUP_PALETTE.length].dot}`} />
                {group.title}
              </span>
            ))}
          </div>
        )}
        <div className="doc-scroll flex-1 overflow-y-auto px-6 py-6">
          <div className="whitespace-pre-wrap break-words text-sm leading-7">
            {fullText ? parts.map((part, index) => {
              if (!part.highlighted) return <span key={index}>{part.text}</span>;
              const isFirst = !assignedFirstRef;
              assignedFirstRef = true;
              const palette = part.groupIndex != null
                ? EVIDENCE_GROUP_PALETTE[part.groupIndex % EVIDENCE_GROUP_PALETTE.length]
                : EVIDENCE_GROUP_PALETTE[0];
              return (
                <mark
                  key={index}
                  ref={isFirst ? firstHighlightRef : undefined}
                  className={`rounded px-0.5 py-0.5 text-slate-950 ring-1 ${palette.mark}`}
                  data-quote-index={part.quoteIndex}
                  data-group-index={part.groupIndex}
                >
                  {part.text}
                </mark>
              );
            }) : <span className="text-muted-foreground">회의록 원문이 없습니다.</span>}
          </div>
        </div>
      </aside>
    </div>
  );
}
