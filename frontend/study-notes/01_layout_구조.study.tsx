// ============================================================================
// 📘 학습용 사본 — 실제 앱에서 쓰이지 않습니다 (아무 데서도 import 안 됨, 빌드에 영향 없음).
// 원본:
//   - src/app/layout.tsx               (앱 전체를 감싸는 최상위 껍데기)
//   - src/app/(dashboard)/layout.tsx   (로그인 필요한 화면들의 공통 문지기)
// 이 파일을 고쳐도 실제 앱은 안 바뀝니다 — 공부용으로 마음껏 낙서하세요.
// ============================================================================

// -----------------------------------------------------------------------------
// [1] src/app/layout.tsx — "가장 바깥쪽 껍데기"
//
// Next.js 규칙: app/ 폴더 바로 밑의 layout.tsx는 이 앱의 모든 페이지를 감싼다.
// 즉 /login, /documents, /tasks... 뭘 열어도 결국 이 파일의 <body> 안에서 그려진다.
// -----------------------------------------------------------------------------

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";                      // 전역 CSS(색상, 글래스모피즘 등) — 이 파일 한 번만 불러오면 앱 전체에 적용됨
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/lib/auth";
import { QueryProvider } from "@/lib/queryClient";

const inter = Inter({ subsets: ["latin"] });

// 브라우저 탭 제목("헤이짜비")과 검색엔진용 설명. React 컴포넌트가 아니라
// 그냥 값을 export하는 것뿐 — Next.js가 이 값을 읽어서 <title> 태그를 자동으로 만들어준다.
export const metadata: Metadata = {
  title: "헤이짜비",
  description: "AI-powered Task Management System",
};

// 💡 "children"이 뭔지가 이 파일 이해의 전부다.
// children = "지금 실제로 보고 있는 페이지 내용" 이라고 생각하면 된다.
// 브라우저 주소가 /documents 면 children 자리에 documents 페이지가 통째로 들어오고,
// /tasks 면 tasks 페이지가 들어온다. RootLayout 자신은 페이지 내용을 전혀 모른다 —
// 그냥 "얘를 어떤 것들로 감싸줄지"만 결정한다.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;   // "React가 그릴 수 있는 아무거나"라는 뜻의 타입
}>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body className={inter.className}>

        {/* 감싸는 순서 = 바깥에서 안으로. 안쪽 Provider는 바깥쪽 Provider가 만들어둔
            값을 자유롭게 쓸 수 있다(반대는 안 됨). 순서 자체는 의미가 있는 경우가 많은데,
            여긴 서로 독립적이라 순서를 바꿔도 문제는 없다. */}

        <ThemeProvider           /* ① 다크모드/라이트모드 상태를 앱 전체에 뿌린다 */
          attribute="class"
          defaultTheme="system"  // 기본값: OS 설정을 따라간다
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>        {/* ② 서버에서 받아온 데이터를 캐싱해주는 라이브러리(react-query) 세팅 */}
            <AuthProvider>       {/* ③ "지금 누가 로그인했는지"를 앱 전체가 알 수 있게 함 */}
              {children}         {/* ④ 실제 페이지가 여기 끼워진다 — 위 ①②③이 전부 준비된 다음에 그려짐 */}
            </AuthProvider>
          </QueryProvider>
        </ThemeProvider>

      </body>
    </html>
  );
}


// -----------------------------------------------------------------------------
// [2] src/app/(dashboard)/layout.tsx — "로그인 안 하면 못 들어오는 구역의 문지기"
//
// 폴더 이름이 (dashboard)처럼 소괄호로 싸여 있으면, 이건 URL에는 안 나타나는
// "그룹 폴더"다. 즉 이 밑에 있는 documents/page.tsx는 /documents로 접속되고
// (/dashboard/documents가 아님) — 대신 이 layout.tsx를 전부 공통으로 거친다.
// -----------------------------------------------------------------------------

"use client";
// 💡 파일 맨 위의 "use client"가 뭔지: Next.js는 기본적으로 컴포넌트를 서버에서
// 미리 그려서(server component) 보내는데, useState/useEffect처럼 "브라우저에서
// 실시간으로 반응해야 하는" 코드는 그게 안 된다. "use client"를 적으면 "이 파일은
// 브라우저에서 직접 실행해야 해"라고 Next.js에 알려주는 것 — 이 프로젝트의 화면
// 대부분이 상호작용이 있어서 거의 다 "use client"가 붙어있다.

import { MobileNav } from "@/components/layout/MobileNav";
import { SidebarProvider } from "@/components/layout/SidebarContext";
import { DashboardContent } from "@/components/layout/DashboardContent";
import { useAuth } from "@/lib/auth";           // 위 RootLayout의 AuthProvider가 만들어둔 로그인 정보 창고
import { useEffect } from "react";
import { useRouter } from "next/navigation";     // 코드로 페이지 이동시킬 때 씀 (링크 클릭이 아니라 "강제로 보내기")

function DashboardLayout({
  children,           // /documents, /tasks 등 실제 화면 내용
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  // user: 로그인 안 했으면 null, 로그인했으면 { id, name, role: "PM"|"MEMBER", ... }
  // isLoading: "로그인 여부를 아직 확인 중"인 아주 짧은 순간(localStorage 읽는 동안)

  const router = useRouter();

  // 💡 useEffect(fn, [의존성 배열]) 다시 한번 정리:
  //   - []  → 화면이 처음 나타났을 때 딱 한 번
  //   - [a, b] → a나 b 값이 바뀔 때마다 (지금 이 경우)
  //   - 배열 자체를 안 쓰면 → 화면이 다시 그려질 때마다 매번 (거의 안 씀, 무한루프 위험)
  useEffect(() => {
    if (!isLoading && !user) {
      // "확인이 끝났는데(로딩 아님) 로그인한 사람이 없다" → 로그인 화면으로 쫓아냄
      router.push("/login");
    } else if (user?.isFirstLogin) {
      // 로그인은 했는데 첫 로그인(비밀번호 변경 등 온보딩 필요) → 온보딩으로
      router.push("/onboarding");
    }
  }, [user, isLoading, router]);

  // 💡 여기가 핵심 트릭: 위 useEffect는 "리다이렉트를 예약"할 뿐, 화면을 즉시
  // 멈추지는 않는다(React는 그런 식으로 안 동작함). 그래서 아래처럼 "아직 확인 안
  // 됐거나 로그인 안 된 상태"면 진짜 페이지 내용(children) 대신 로딩 화면을
  // 보여줘서, 잠깐이라도 "로그인 안 한 사람에게 진짜 화면이 스쳐 보이는" 걸 막는다.
  if (isLoading || !user || user.isFirstLogin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
        로딩 중...
      </div>
    );
  }

  // 여기까지 왔다는 건 "로그인 확인 끝, user 있음, 첫 로그인도 아님" → 진짜 화면 그리기
  return (
    <SidebarProvider>                 {/* 사이드바 접힘/펼침 같은 UI 상태 공유 */}
      <div className="min-h-screen bg-background">
        <DashboardContent>
          {children}                  {/* documents/page.tsx 등 실제 화면이 여기 */}
        </DashboardContent>
        <MobileNav />
      </div>
    </SidebarProvider>
  );
}

// -----------------------------------------------------------------------------
// 🧪 스스로 확인해볼 것
// 1. RootLayout의 children과 DashboardLayout의 children은 같은 개념인데 왜 두 번 나올까?
//    → Next.js는 layout을 폴더 계층대로 "중첩"시킨다.
//      RootLayout(children = DashboardLayout(children = 실제 페이지))
//      즉 실제 페이지는 두 겹의 layout에 감싸인 채로 그려진다.
// 2. 만약 useEffect의 의존성 배열을 []로 바꾸면 어떻게 될까?
//    → 로그인 직후에도 자동으로 재검사가 안 일어나서, 화면 전환이 안 될 수 있다.
//      (이런 실수를 실제로 이 저장소에서 몇 번 겪고 고친 이력이 있다 — 코드 주석 참고)
// -----------------------------------------------------------------------------
