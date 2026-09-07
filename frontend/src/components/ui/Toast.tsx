"use client";

import { useEffect } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

export type ToastVariant = "success" | "error";

// 에이전트 생성이 끝났을 때 "생성이 완료되었습니다" 같은 걸 알려주는 용도로 시작했는데,
// 화면 곳곳의 실패 처리가 alert()라 브라우저 기본 모달이 튀어나오는 게 화면 톤과
// 안 맞고 다른 화면과도 스타일이 달랐다 — 실패 메시지도 이 컴포넌트로 통일하기 위해
// variant="error"(빨간 아이콘, 조금 더 오래 노출)를 추가했다. confirm()과 달리
// 사용자가 직접 닫을 필요 없이 잠깐 떴다가 자동으로 사라진다.
export function Toast({
  message, onDismiss, duration, variant = "success",
}: {
  message: string | null;
  onDismiss: () => void;
  duration?: number;
  variant?: ToastVariant;
}) {
  const effectiveDuration = duration ?? (variant === "error" ? 3200 : 2200);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, effectiveDuration);
    return () => clearTimeout(timer);
  }, [message, effectiveDuration, onDismiss]);

  if (!message) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-2 px-4 py-3 rounded-xl bg-foreground text-background text-sm font-semibold shadow-2xl">
      {variant === "error" ? (
        <XCircle className="w-4 h-4 text-red-400 shrink-0" />
      ) : (
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      )}
      {message}
    </div>
  );
}
