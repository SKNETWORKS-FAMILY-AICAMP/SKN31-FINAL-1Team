"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, CheckCircle, Menu, X, Settings, LogOut, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "@/components/layout/Sidebar";
import { useAuth } from "@/lib/auth";

export function MobileNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const isPM = user?.role === "PM";
  // "메뉴" 버튼이 onClick 없이 방치돼 있어서 모바일에서 문서생성/업무관리/히스토리로
  // 갈 방법이 아예 없었다 — 사이드바와 같은 목록을 보여주는 드로어를 붙인다.
  const [menuOpen, setMenuOpen] = useState(false);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  // 직원관리는 PM 전용(Sidebar.tsx와 같은 이유) — 드로어 목록에서도 같은 기준으로 숨긴다.
  const visibleNavItems = NAV_ITEMS.filter(item => item.href !== "/members" || isPM);

  return (
    <>
      <div className="md:hidden fixed bottom-0 left-0 w-full glass border-t border-border z-50">
        <nav className="flex items-center justify-around p-3">
          <Link href="/" className={cn("flex flex-col items-center gap-1", pathname === "/" ? "text-primary" : "text-foreground/70")}>
            <LayoutDashboard className="w-5 h-5" />
            <span className="text-[10px] font-medium">대시보드</span>
          </Link>
          {isPM && (
            <Link href="/members" className={cn("flex flex-col items-center gap-1", pathname === "/members" ? "text-primary" : "text-foreground/70")}>
              <Users className="w-5 h-5" />
              <span className="text-[10px] font-medium">멤버</span>
            </Link>
          )}
          {/* 데스크톱 대시보드/승인함 페이지 제목과 같은 "승인" 용어로 통일 — 예전엔 여기만 "결재"라고 써서
              같은 화면을 다른 이름으로 부르는 바람에 헷갈렸다 */}
          <Link href="/approvals" className={cn("flex flex-col items-center gap-1", pathname === "/approvals" ? "text-primary" : "text-foreground/70")}>
            <CheckCircle className="w-5 h-5" />
            <span className="text-[10px] font-medium">승인</span>
          </Link>
          <button onClick={() => setMenuOpen(true)} className="flex flex-col items-center gap-1 text-foreground/70">
            <Menu className="w-5 h-5" />
            <span className="text-[10px] font-medium">메뉴</span>
          </button>
        </nav>
      </div>

      {menuOpen && typeof document !== "undefined" && createPortal(
        <div className="md:hidden fixed inset-0 z-[100] flex items-end">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setMenuOpen(false)} />
          <div className="relative w-full bg-background border-t border-border rounded-t-2xl p-4 pb-8 animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold">메뉴</h3>
              <button onClick={() => setMenuOpen(false)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2 mb-2">
              {visibleNavItems.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    "flex flex-col items-center gap-1.5 py-3 rounded-xl text-xs font-semibold transition-colors",
                    isActive(href) ? "bg-primary/10 text-primary" : "bg-black/5 dark:bg-white/5 text-foreground/80"
                  )}
                >
                  <Icon className="w-5 h-5" />
                  {label}
                </Link>
              ))}
            </div>
            <div className="border-t border-border pt-2 flex flex-col gap-1">
              <Link href="/profile" onClick={() => setMenuOpen(false)} className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">
                <UserIcon className="w-4 h-4" /> 프로필
              </Link>
              <Link href="/settings" onClick={() => setMenuOpen(false)} className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">
                <Settings className="w-4 h-4" /> 설정
              </Link>
              <button onClick={() => { setMenuOpen(false); logout(); }} className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-red-500 hover:bg-red-500/10 text-left">
                <LogOut className="w-4 h-4" /> 로그아웃
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
