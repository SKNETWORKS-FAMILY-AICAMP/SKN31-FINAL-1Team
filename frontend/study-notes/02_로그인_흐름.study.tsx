// ============================================================================
// 📘 학습용 사본 — 실제 앱에서 쓰이지 않습니다. 원본: src/lib/auth.tsx
// (원본 전체를 다 옮기지 않고, 배워야 할 핵심 3개 함수만 골라서 촘촘히 설명합니다.
//  devToggleRole/completeOnboarding 등 나머지는 원본 파일에서 직접 확인하세요.)
// ============================================================================

"use client";
import React, { createContext, useContext, useState, useEffect } from "react";
import { apiFetch } from "@/lib/api/client";
import { toUser } from "@/lib/api/mappers";

// 💡 TypeScript 타입 복습: "role"의 타입이 문자열 아무거나가 아니라
// "PM" | "MEMBER" 딱 두 가지 중 하나로 고정되어 있다. 이렇게 해두면
// 코드 어디선가 user.role === "ADMIN" 처럼 오타를 내면 즉시 에러로 잡힌다.
export type User = {
  id: string;
  email: string;
  name: string;
  role: "PM" | "MEMBER";
  isFirstLogin: boolean;
};

// 💡 "창고"의 타입 — 이 창고에 들어갈 수 있는 값과 함수들을 미리 정의.
// login/logout이 "함수 타입"으로 선언되어 있는 걸 눈여겨보세요:
// (email: string, password: string) => Promise<void>
//   = "문자열 두 개를 받아서, 끝나면 아무 값도 안 주는 비동기 작업"
type AuthContextType = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  completeOnboarding: (name: string, info: any) => Promise<void>;
  devToggleRole: () => Promise<void>;
};

// 💡 createContext — React의 "전역 창고 만들기" 도구.
// undefined를 기본값으로 주는 이유: "Provider 밖에서 잘못 쓰면 바로 에러 내고 싶어서"
// (맨 아래 useAuth() 함수에서 이 undefined를 체크해서 친절한 에러를 던짐)
const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // 이 두 줄이 "창고 안의 실제 내용물"이다. useState로 만든 값이 바뀌면
  // 이 창고를 쓰는 모든 화면이 자동으로 다시 그려진다.
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // ---------------------------------------------------------------------
  // ① 앱이 켜지자마자: "혹시 이미 로그인했던 기록이 있나?" 확인
  // ---------------------------------------------------------------------
  useEffect(() => {
    // localStorage = 브라우저에 남는 저장공간(새로고침해도 안 지워짐).
    // 로그인 성공 시 저장해둔 사용자 정보를 여기서 다시 꺼낸다.
    const stored = localStorage.getItem("hz_session");
    if (stored) {
      setUser(JSON.parse(stored));   // 문자열로 저장했던 걸 다시 객체로 변환
    }
    setIsLoading(false);             // "확인 끝났다" 표시 — 01번 파일의 DashboardLayout이 이 값을 봄
  }, []);   // [] = 앱이 처음 켜질 때 딱 한 번만

  // ---------------------------------------------------------------------
  // ② login() — 로그인 화면의 버튼이 부르는 함수
  // ---------------------------------------------------------------------
  const login = async (email: string, password: string) => {
    // 1단계: CSRF 토큰 먼저 받아온다.
    // 💡 CSRF가 뭔지 몰라도 되지만 감은 잡아두자: "쓰기 요청(POST 등)을 보낼 때는
    // 서버가 준 특별한 값을 같이 보내야 진짜 이 사이트에서 보낸 요청인지 확인할 수 있다"
    // — 이게 없으면 다른 사이트가 몰래 우리 서버에 요청을 보내는 공격을 막기 어렵다.
    await apiFetch("/api/users/csrf/");

    // 2단계: 아이디/비밀번호를 서버로 전송. 성공하면 서버가 로그인 쿠키를 심어준다
    // (우리가 직접 토큰을 저장하는 게 아니라 — 브라우저가 자동으로 관리).
    try {
      await apiFetch("/api/users/login/", {
        method: "POST",
        body: JSON.stringify({ username: email, password }),
      });
    } catch (err: any) {
      // apiFetch는 서버가 에러를 주면 그냥 JS의 Error를 throw한다(03번 파일에서 자세히).
      // 여기서 다시 잡아서 좀 더 친절한 메시지로 바꿔 다시 던진다 —
      // 이걸 던지면 로그인 화면 컴포넌트의 catch에서 받아서 화면에 보여줄 수 있다.
      throw new Error(err.message || "로그인에 실패했습니다.");
    }

    // 3단계: 로그인 응답에는 "role"(PM/MEMBER) 정보가 없어서, 내 정보를 한 번 더 조회.
    const profile = await apiFetch<any>("/api/users/me/");
    const mappedUser = toUser(profile);  // 서버가 준 모양 → 화면이 쓰는 User 타입으로 변환

    // 4단계: 창고에 저장 → 이 순간 앱 전체가 "로그인 상태"로 바뀐다.
    setUser(mappedUser);
    localStorage.setItem("hz_session", JSON.stringify(mappedUser)); // 새로고침해도 유지되게
  };

  // ---------------------------------------------------------------------
  // ③ 로그인 유지 확인 — 30초마다 "나 아직 로그인 상태 맞나?" 서버에 물어봄
  // ---------------------------------------------------------------------
  // 왜 필요한가: 로그인해 있는 동안 PM이 이 계정을 정지시킬 수도 있는데,
  // 사용자가 화면을 그냥 보고만 있으면(API 호출이 없으면) 그걸 알 방법이 없다.
  // 그래서 "아무것도 안 해도 30초마다 확인"하는 타이머를 둔다.
  useEffect(() => {
    if (!user) return;   // 로그인 안 한 상태면 확인할 필요 없음

    const checkSession = async () => {
      let res: Response;
      try {
        res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/users/me/`, {
          credentials: "include",
        });
      } catch {
        return; // 네트워크가 잠깐 끊긴 것뿐일 수 있으니, 이번엔 넘어가고 다음 30초에 재시도
      }

      if (res.status === 401 || res.status === 403) {
        // "진짜 세션 만료"인지 "그냥 access 토큰만 만료(자동으로 재발급 가능)"인지
        // 구분하기 위해, apiFetch를 한 번 더 태워본다 — apiFetch는 자체적으로
        // 401을 만나면 refresh를 시도하기 때문(03번 파일에서 봄).
        try {
          await apiFetch("/api/users/me/");
          return; // refresh로 살아났다 → 계속 로그인 상태 유지
        } catch {
          // refresh도 실패 = 진짜 로그아웃된 것 → 강제 로그아웃 처리
          setUser(null);
          localStorage.removeItem("hz_session");
          window.location.href = "/login";
        }
      }
      // 200이거나, 401/403이 아닌 다른 오류(서버 일시 다운 등)는 계정 문제가 아니므로 무시
    };

    const interval = setInterval(checkSession, 30000); // 30000ms = 30초마다 반복 실행

    // 💡 useEffect가 "return 함수"를 주면, 이 useEffect가 다시 실행되기 직전이나
    // 컴포넌트가 사라질 때 그 함수가 실행된다("청소" 역할). 여기선 타이머를 꼭
    // 꺼줘야 한다 — 안 그러면 로그아웃한 뒤에도 계속 타이머가 살아서 메모리가 샌다.
    return () => clearInterval(interval);
  }, [user]);  // user가 바뀔 때마다(로그인/로그아웃 시점마다) 이 감시 로직을 새로 건다

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout: () => {}, completeOnboarding: async () => {}, devToggleRole: async () => {} }}>
      {children}
    </AuthContext.Provider>
  );
}

// 💡 useAuth() — 다른 컴포넌트들이 창고에 접근하는 유일한 방법.
// Context를 직접 쓰지 않고 이렇게 함수로 한 번 감싸두면, "Provider 밖에서 잘못
// 쓰면 에러"라는 안전장치를 여기 한 곳에서만 관리할 수 있다.
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// -----------------------------------------------------------------------------
// 🧪 스스로 확인해볼 것
// 1. login()의 4단계는 왜 순서가 중요할까? (2단계 실패하면 3단계로 안 넘어가는 이유는?)
//    → async/await로 쓴 코드는 위에서 아래로 "한 줄씩 끝나야 다음 줄"이 실행된다.
//      await가 실패(reject)하면 그 아래 코드는 실행 안 되고 catch로 바로 튄다.
// 2. checkSession의 30초 타이머는 로그인 화면(아직 user가 없는 상태)에서도 돌까?
//    → 아니다. useEffect 맨 위에 `if (!user) return;`이 있어서, user가 없으면
//      타이머 자체를 안 건다.
// -----------------------------------------------------------------------------
