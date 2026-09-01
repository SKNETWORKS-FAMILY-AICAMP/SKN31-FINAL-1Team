"use client";

import { useEffect } from "react";
import { CheckCircle2 } from "lucide-react";

// 에이전트 생성이 끝났을 때 "생성이 완료되었습니다" 같은 걸 알려주는 용도 — confirm()과 달리
// 사용자가 직접 닫을 필요 없이 잠깐 떴다가 자동으로 사라진다(성공 알림이라 확인을 요구할
// 이유가 없음). 여러 화면(문서생성/업무분배)에서 공용으로 쓴다.
export function Toast({
  message, onDismiss, duration = 2200,
}: {
  message: string | null;
  onDismiss: () => void;
  duration?: number;
}) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [message, duration, onDismiss]);

  if (!message) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-2 px-4 py-3 rounded-xl bg-foreground text-background text-sm font-semibold shadow-2xl">
      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      {message}
    </div>
  );
}
