"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { Sidebar, NAV_ITEMS } from "@/components/layout/Sidebar";
import { useSidebar } from "@/components/layout/SidebarContext";
import { cn } from "@/lib/utils";
import { NotificationBell } from "@/components/layout/NotificationBell";

export function DashboardContent({ children }: { children: React.ReactNode }) {
  const { isOpen } = useSidebar();
  const pathname = usePathname();
  // 예전엔 페이지마다 각자 큰 제목(h1)을 본문 안에 따로 그려서 사이드바 접기 버튼과 높이가
  // 안 맞고 탭마다 위아래로 들쭉날쭉했다 — 사이드바의 NAV_ITEMS를 그대로 재사용해 상단 공용
  // 바에서 그 버튼과 같은 줄에 제목을 보여준다(사용자 요청).
  const currentNavItem = NAV_ITEMS.find(item => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)));

  return (
    <>
      <Sidebar />
      <div
        className={cn(
          "pb-16 md:pb-0 flex flex-col min-h-screen transition-[padding] duration-300 ease-in-out",
          isOpen ? "md:pl-64" : "md:pl-16"
        )}
      >
        {/* 페이지마다 따로 헤더를 만드는 이 앱 구조상 "모든 탭에서 항상 상단 우측"에 두려면
            공용 바가 필요하다(사용자 요청 — 처음엔 사이드바에 뒀다가 위치를 옮김).
            높이(h-16)를 사이드바 헤더(Sidebar.tsx의 h-16)와 맞춰서, 페이지 제목이 사이드바
            접기 버튼과 같은 줄에 정확히 정렬되게 한다(사용자 요청). */}
        <div className="h-16 shrink-0 flex items-center justify-between px-4 md:px-8 border-b border-border">
          {currentNavItem ? (
            <h1 className="flex items-center gap-2 text-lg font-bold text-foreground tracking-tight">
              <currentNavItem.icon className="w-5 h-5 text-primary" />
              {currentNavItem.label}
            </h1>
          ) : <span />}
          <NotificationBell />
        </div>
        {/* 상하 여백을 좌우보다 확 줄임 — 알림 바 아래 여백이 과하다는 피드백, 한 번 줄이고도
            더 줄여달라는 요청이 있어 최종적으로 원래(p-8)의 1/4 수준까지 좁힘(모든 탭 공용) */}
        <main className="flex-1 px-4 md:px-8 py-1.5 md:py-2 min-w-0 flex flex-col">
          {children}
        </main>
      </div>
    </>
  );
}
