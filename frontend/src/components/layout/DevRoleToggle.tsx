"use client";

// DEV ONLY — segmented toggle to switch the current session between PM and a
// real team member account instantly, so both role-specific views (with real
// per-user data) can be tested without re-logging in. Safe to delete this
// file (and its usage in Sidebar's footer) before ship.
//
// 이전엔 화면 우상단에 고정 배지로 떠 있었는데, 직원관리 페이지의 "직원 추가" 버튼을
// 가려버리는 문제가 있어 좌측 네비게이션 하단(프로필 행 바로 위)으로 옮겼다.

import { useAuth } from "@/lib/auth";
import { ShieldCheck, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function DevRoleToggle({ isOpen }: { isOpen: boolean }) {
  const { user, devToggleRole } = useAuth();
  if (!user) return null;

  const isPM = user.role === "PM";

  if (!isOpen) {
    // 사이드바가 접혀 있을 때는 자리가 없으니 아이콘 하나로 눌러서 순환 전환한다
    return (
      <button
        onClick={devToggleRole}
        title={`DEV: ${isPM ? "PM" : "일반유저"} (클릭하여 전환)`}
        className="w-full flex items-center justify-center py-1.5 rounded-lg bg-yellow-400 hover:bg-yellow-300 text-black transition-colors group relative"
      >
        {isPM ? <ShieldCheck className="w-4 h-4" /> : <UserIcon className="w-4 h-4" />}
        <span className="absolute left-full ml-4 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
          DEV: {isPM ? "PM" : "일반유저"}
        </span>
      </button>
    );
  }

  return (
    <div className="w-full flex items-center gap-1.5 p-1 rounded-full bg-yellow-400 border border-yellow-500">
      <span className="pl-1.5 pr-0.5 text-[10px] font-black text-black/60 uppercase tracking-wider shrink-0">DEV</span>
      <button
        onClick={() => !isPM && devToggleRole()}
        className={cn(
          "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-full text-xs font-bold transition-colors",
          isPM ? "bg-black text-yellow-300" : "text-black/60 hover:text-black"
        )}
      >
        <ShieldCheck className="w-3.5 h-3.5" /> PM
      </button>
      <button
        onClick={() => isPM && devToggleRole()}
        className={cn(
          "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-full text-xs font-bold transition-colors",
          !isPM ? "bg-black text-yellow-300" : "text-black/60 hover:text-black"
        )}
      >
        <UserIcon className="w-3.5 h-3.5" /> 일반유저
      </button>
    </div>
  );
}
