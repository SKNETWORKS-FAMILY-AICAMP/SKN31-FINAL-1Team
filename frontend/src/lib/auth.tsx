"use client";

import React, { createContext, useContext, useState, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api/client";
import { toUser } from "@/lib/api/mappers";

export type User = {
  id: string;
  email: string;
  name: string;
  role: "PM" | "MEMBER";
  isFirstLogin: boolean;
};

type AuthContextType = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  completeOnboarding: (name: string, info: any) => Promise<void>;
  /** DEV ONLY — swaps the current session to a real team member (or back to PM), no re-login. Remove before ship. */
  devToggleRole: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // 첫 로그인(온보딩) 때만 쓰는 값 — 온보딩에서 비밀번호를 바꾸려면 백엔드
  // ChangePasswordView가 "현재 비밀번호"를 요구하는데, 로그인 성공 후에는 그
  // 비밀번호를 어디에도 저장해두지 않아서(보안상 당연히 맞는 설계) 온보딩
  // 단계에서 다시 쓸 방법이 없었다. localStorage 등에 영구 저장하면 보안
  // 문제이므로, useRef로 이 세션의 메모리에만 잠깐 들고 있다가 온보딩이
  // 끝나면(성공/실패 무관) 바로 지운다 — 새로고침하면 사라짐.
  const pendingPasswordRef = useRef<string | null>(null);

  // Still use localStorage for session persistence in this MVP
  useEffect(() => {
    const stored = localStorage.getItem("hz_session");
    if (stored) {
      setUser(JSON.parse(stored));
    }
    setIsLoading(false);
  }, []);

  // 로그인해 있는 동안 PM이 이 계정을 휴직/퇴사/잠금 처리할 수 있다 — 그 순간 즉시 화면이
  // 튕기진 않지만(access 토큰 자체는 만료 전까지 유효한 서명이므로), 다음 API 호출부터는
  // 서버가 막는다. 여기서는 API 호출이 없는 유휴 상태에서도 놓치지 않도록 주기적으로
  // GET /api/users/me/ 를 불러 계정이 여전히 유효한지 확인하고, 아니면 강제 로그아웃한다.
  useEffect(() => {
    if (!user) return;
    // 2026-09-01: apiFetch는 네트워크 오류와 401/403을 구분 안 하고 둘 다 throw하는데, 예전엔
    // 여기서 그 둘을 구분 없이 곧장 강제 로그아웃시켰다 — WSL 개발 환경처럼 네트워크가 잠깐씩
    // 끊기는 상황에서 "계속 로그아웃된다"는 걸 사용자가 실제로 겪었다. access 토큰은 apiFetch가
    // 401을 만나면 자체적으로 refresh 후 재시도하므로, 여기서 또 401을 받는다는 건 refresh
    // 토큰까지 진짜 만료/무효라는 뜻 — 그때만 로그아웃한다. 그 외(네트워크 오류, 서버 일시 다운
    // 등)는 다음 주기에 다시 시도하고 이번엔 그냥 넘어간다.
    const checkSession = async () => {
      let res: Response;
      try {
        res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/users/me/`, {
          credentials: "include",
        });
      } catch {
        return; // 네트워크 오류 — 일시적일 수 있으니 로그아웃시키지 않고 다음 주기에 재시도
      }
      if (res.status === 401 || res.status === 403) {
        // apiFetch를 한 번 더 태워서 refresh 시도까지 확실히 거친 뒤에도 401이면 진짜 만료된 것
        try {
          await apiFetch("/api/users/me/");
          return; // refresh로 살아났으면 그냥 계속 진행
        } catch (err: any) {
          // 2026-09-07: "동시 로그인 1개만 허용" 기능이 추가되면서, 다른 곳에서 같은 계정으로
          // 로그인하면 이 세션이 강제 종료된다 — 아무 설명 없이 로그인 화면으로 튕기면 사용자는
          // 왜 로그아웃됐는지 알 방법이 없다(실제로 겪음). 백엔드가 이미 detail 메시지로 사유를
          // 내려주므로(예: "다른 기기에서 로그인되어 세션이 종료되었습니다"), 그걸 로그인
          // 화면에 전달해서 보여준다.
          if (err?.message) {
            sessionStorage.setItem("hz_logout_reason", err.message);
          }
          setUser(null);
          localStorage.removeItem("hz_session");
          window.location.href = "/login";
        }
      }
      // 200이거나 401/403이 아닌 다른 오류(5xx 등)는 계정 문제가 아니므로 무시
    };
    const interval = setInterval(checkSession, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const login = async (email: string, password: string) => {
    // 2026-08-31: 토큰을 localStorage 대신 HttpOnly 쿠키로 옮기면서, 로그인(쓰기 요청) 전에
    // csrftoken 쿠키를 먼저 확보해야 한다 — Django의 CSRF 검증은 X-CSRFToken 헤더 값이
    // csrftoken 쿠키 값과 일치하는지 보는데, 첫 로그인 시도 시점엔 그 쿠키가 아직 없다.
    await apiFetch("/api/users/csrf/");

    type LoginResponse = {
      message: string;
      user: { id: number | string; username: string; full_name: string; emp_no: string | null };
    };
    try {
      await apiFetch<LoginResponse>("/api/users/login/", {
        method: "POST",
        body: JSON.stringify({ username: email, password }),
      });
    } catch (err: any) {
      throw new Error(err.message || "로그인에 실패했습니다.");
    }
    // access/refresh 토큰은 이제 서버가 Set-Cookie로 내려준다 — 여기서 직접 저장할 게 없다.

    // 로그인 응답(UserSimpleSerializer)에는 role 정보가 없다 — 화면의 PM/MEMBER 분기에 필요한
    // role_code는 GET /api/users/me/ (UserDetailSerializer)에만 있어서 한 번 더 불러온다.
    const profile = await apiFetch<any>("/api/users/me/");
    const mappedUser = toUser(profile);

    // 첫 로그인이면 온보딩에서 비밀번호 변경 API에 "현재 비밀번호"로 다시 써야 한다
    // (위 pendingPasswordRef 선언부 설명 참고). 첫 로그인이 아니면 온보딩을 안 타므로
    // 굳이 들고 있을 필요 없음 — 비워둔다.
    pendingPasswordRef.current = mappedUser.isFirstLogin ? password : null;

    setUser(mappedUser);
    localStorage.setItem("hz_session", JSON.stringify(mappedUser));
  };

  const logout = () => {
    // 쿠키(access/refresh)는 HttpOnly라 프론트가 직접 지울 수 없다 — 서버가 응답에서
    // Set-Cookie로 만료시켜야 한다(users/views.py LogoutView의 clear_auth_cookies).
    apiFetch("/api/users/logout/", { method: "POST" }).catch(() => {});

    setUser(null);
    localStorage.removeItem("hz_session");
    window.location.href = "/login";
  };

  // DEV ONLY — 재로그인 없이 다른 팀원 계정으로 세션을 바꿔본다.
  // 2026-08-31: 토큰이 HttpOnly 쿠키로 바뀌면서 "프론트 JS가 원래 PM 토큰을 보관해뒀다가
  // 되돌린다"는 방식이 아예 불가능해졌다(JS가 쿠키 값을 읽을 수 없으므로) — 대신 서버가
  // 원래 토큰을 dev_original_* 쿠키에 보관해두고, 복귀는 전용 엔드포인트
  // (POST /api/users/dev-stop-impersonate/)가 그걸 읽어 되돌린다.
  const devToggleRole = async () => {
    if (!user) return;

    if (user.role === "PM") {
      try {
        const employees = await apiFetch<any[]>("/api/users/");
        const nonPm = employees
          .filter((u: any) => !(u.role_info?.code_id === "ADMIN" || u.is_staff))
          .sort((a: any, b: any) => (a.username || "").localeCompare(b.username || ""));
        if (nonPm.length === 0) {
          console.error("dev-impersonate: 전환할 일반 유저 계정이 없습니다.");
          return;
        }
        await apiFetch(`/api/users/${nonPm[0].id}/impersonate/`, { method: "POST" });

        const profile = await apiFetch<any>("/api/users/me/");
        const preview = toUser(profile);
        setUser(preview);
        localStorage.setItem("hz_session", JSON.stringify(preview));
      } catch (err) {
        console.error("dev-impersonate failed:", err);
      }
      return;
    }

    try {
      await apiFetch("/api/users/dev-stop-impersonate/", { method: "POST" });

      const profile = await apiFetch<any>("/api/users/me/");
      const pmUser = toUser(profile);
      setUser(pmUser);
      localStorage.setItem("hz_session", JSON.stringify(pmUser));
    } catch (err) {
      console.error("dev-stop-impersonate failed:", err);
    }
  };

  // 2026-09-10: 이 함수가 호출하던 "/api/auth/onboarding"은 예전 Next.js
  // 프로토타입(heyzzabi2) 시절의 API Route였고, 지금 백엔드는 Django라 이 경로가
  // 존재하지 않는다 — 온보딩 자체가 항상 실패하고 있었다(실제로 확인). 실제
  // 존재하는 두 엔드포인트로 나눠서 호출하도록 고친다:
  //   1) PATCH /api/users/me/            — 이름/부서/연락처 저장
  //   2) PATCH /api/users/me/change-password/ — 비밀번호 변경(이 호출이 서버에서
  //      is_onboarded=True로 전환해준다, users/views.py ChangePasswordView 참고)
  const completeOnboarding = async (
    name: string,
    info: { lastName: string; firstName: string; newPassword: string; phone?: string; deptCode?: string }
  ) => {
    if (!user) return;

    await apiFetch("/api/users/me/", {
      method: "PATCH",
      body: JSON.stringify({
        last_name: info.lastName,
        first_name: info.firstName,
        phone: info.phone || null,
        dept_code: info.deptCode || null,
      }),
    });

    // change-password는 "현재 비밀번호" 확인이 필요하다 — 로그인 때 딱 한 번
    // 메모리에 잠깐 담아둔 값(pendingPasswordRef, login() 참고)을 여기서 쓴다.
    const currentPassword = pendingPasswordRef.current;
    if (!currentPassword) {
      throw new Error("로그인 정보가 만료되었습니다. 다시 로그인한 뒤 온보딩을 진행해주세요.");
    }
    await apiFetch("/api/users/me/change-password/", {
      method: "PATCH",
      body: JSON.stringify({ current_password: currentPassword, new_password: info.newPassword }),
    });
    pendingPasswordRef.current = null; // 다 썼으니 메모리에서 바로 지움

    const updatedUser = { ...user, name, isFirstLogin: false };
    setUser(updatedUser);
    localStorage.setItem("hz_session", JSON.stringify(updatedUser));
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, completeOnboarding, devToggleRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
