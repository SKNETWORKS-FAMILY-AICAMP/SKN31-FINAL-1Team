"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Settings, Users, LayoutDashboard, FileText, Briefcase, History,
  Sun, Moon, PanelLeftClose, PanelLeft, LogOut, User as UserIcon, X
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTheme } from "next-themes";
import { useSidebar } from "@/components/layout/SidebarContext";
import { useAuth } from "@/lib/auth";
import { DevRoleToggle } from "@/components/layout/DevRoleToggle";

// MobileNav의 "메뉴" 드로어도 이 목록을 그대로 재사용한다 — 두 군데서 따로 관리하면
// 메뉴 항목이 하나 추가될 때 모바일에서만 빠지는 사고가 나기 쉽다.
export const NAV_ITEMS = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/documents", label: "문서생성", icon: FileText },
  { href: "/tasks", label: "업무관리", icon: Briefcase },
  { href: "/history", label: "히스토리", icon: History },
  { href: "/members", label: "직원관리", icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const { isOpen, toggle } = useSidebar();
  const { user, logout } = useAuth();
  const isPM = user?.role === "PM";
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  // 직원관리는 팀원 개인정보(연락처/기술스택/재직상태 등)를 다루는 관리 기능이라 PM 전용으로
  // 숨긴다 — 지금까지는 누구나 메뉴에서 보이고 들어갈 수 있었다(사용자가 실제로 보고 발견함).
  const visibleNavItems = NAV_ITEMS.filter(item => item.href !== "/members" || isPM);

  return (
    <aside
      className={cn(
        "fixed top-0 left-0 h-screen bg-black/5 dark:bg-white/5 border-r border-border flex flex-col transition-all duration-300 ease-in-out z-50 backdrop-blur-xl",
        isOpen ? "w-64" : "w-16"
      )}
    >
      {/* Header */}
      <div className="h-16 flex items-center justify-between px-3 border-b border-border">
        {isOpen && (
          <Link href="/" className="flex items-center gap-2 overflow-hidden whitespace-nowrap pl-1 group">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform shadow-md">
              <span className="text-white font-black text-sm tracking-tight">Zz</span>
            </div>
            <span className="font-bold text-base tracking-tight text-foreground group-hover:text-primary transition-colors">
              헤이 짜비
            </span>
          </Link>
        )}
        <button
          onClick={toggle}
          className="p-1.5 rounded-md text-foreground/50 hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors shrink-0 group relative"
          aria-label={isOpen ? "사이드바 닫기" : "사이드바 열기"}
        >
          {isOpen ? <PanelLeftClose className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
        </button>
      </div>

      {/* Primary nav */}
      <div className="flex-1 overflow-y-auto py-6 scrollbar-hide">
        <nav className={cn("space-y-1", isOpen ? "px-3" : "px-2")}>
          {visibleNavItems.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-xl transition-colors group relative font-semibold",
                  isOpen ? "px-3 py-2.5 text-[15px]" : "justify-center py-2.5",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-foreground/70 hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
                )}
              >
                <Icon className="w-5 h-5 shrink-0" />
                {isOpen && <span>{label}</span>}
                {!isOpen && (
                  <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                    {label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer: DEV 롤 토글 / 프로필 / 설정 / 테마 / 로그아웃 */}
      <div className={cn("p-3 border-t border-border flex flex-col gap-1", !isOpen && "items-center")}>
        <DevRoleToggle isOpen={isOpen} />

        <div className={cn("flex items-center", isOpen ? "w-full gap-1" : "flex-col gap-1")}>
          <Link
            href="/profile"
            className={cn(
              "flex items-center gap-3 rounded-xl transition-colors group relative font-semibold min-w-0",
              isOpen ? "flex-1 px-3 py-2.5 text-[15px]" : "justify-center py-2.5",
              isActive("/profile")
                ? "bg-primary/10 text-primary"
                : "text-foreground/70 hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
            )}
          >
            <UserIcon className="w-5 h-5 shrink-0" />
            {isOpen && <span className="truncate">{user?.name ? `${user.name}` : "프로필"}</span>}
            {!isOpen && (
              <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                프로필
              </span>
            )}
          </Link>
          <button
            onClick={() => setShowLogoutConfirm(true)}
            className="p-2.5 rounded-xl text-red-500 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0 group relative"
            aria-label="Logout"
            title="로그아웃"
          >
            <LogOut className="w-5 h-5" />
            {!isOpen && (
              <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 whitespace-nowrap z-50 pointer-events-none">
                로그아웃
              </span>
            )}
          </button>
        </div>

        <div className={cn("flex items-center", isOpen ? "w-full gap-1" : "flex-col gap-1")}>
          <Link
            href="/settings"
            className={cn(
              "flex items-center gap-3 rounded-xl transition-colors group relative font-semibold min-w-0",
              isOpen ? "flex-1 px-3 py-2.5 text-[15px]" : "justify-center py-2.5",
              isActive("/settings")
                ? "bg-primary/10 text-primary"
                : "text-foreground/70 hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
            )}
          >
            <Settings className="w-5 h-5 shrink-0" />
            {isOpen && <span>설정</span>}
            {!isOpen && (
              <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                설정
              </span>
            )}
          </Link>
          {mounted && (
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="p-2.5 rounded-xl text-foreground/70 hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors shrink-0 group relative"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
              {!isOpen && (
                <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 whitespace-nowrap z-50 pointer-events-none">
                  테마 변경
                </span>
              )}
            </button>
          )}
        </div>
      </div>

      {mounted && showLogoutConfirm && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <LogOut className="w-5 h-5" /> 로그아웃
              </h3>
              <button onClick={() => setShowLogoutConfirm(false)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5">
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-6">정말 로그아웃 하시겠습니까?</p>
            <div className="flex gap-3">
              <button onClick={() => setShowLogoutConfirm(false)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={logout}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/20 flex items-center justify-center gap-2"
              >
                <LogOut className="w-4 h-4" /> 로그아웃
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </aside>
  );
}
