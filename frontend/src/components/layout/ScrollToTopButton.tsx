"use client";

import { useEffect, useState } from "react";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

// 페이지를 길게 내린 뒤 다시 맨 위로 스크롤하는 게 오래 걸린다는 피드백 — 일정 거리 이상
// 내려가면 우측 하단에 "위로 가기" 버튼을 띄운다. 이 앱은 페이지 자체(main 안이 아니라
// window)가 스크롤되는 구조라 window.scrollY를 기준으로 삼는다.
export function ScrollToTopButton() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <button
      type="button"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      aria-label="맨 위로 이동"
      title="맨 위로"
      className={cn(
        "fixed bottom-20 md:bottom-6 right-4 md:right-6 z-40 w-11 h-11 rounded-full",
        "bg-primary text-primary-foreground shadow-lg flex items-center justify-center",
        "hover:bg-primary/90 transition-all duration-200",
        visible ? "opacity-100 translate-y-0 pointer-events-auto" : "opacity-0 translate-y-2 pointer-events-none"
      )}
    >
      <ArrowUp className="w-5 h-5" />
    </button>
  );
}
