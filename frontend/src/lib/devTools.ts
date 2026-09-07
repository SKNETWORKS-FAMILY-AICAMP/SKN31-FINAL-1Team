// DEV 롤 토글(계정 미리보기) 기능을 이 배포에서 켤지 여부.
// - 로컬 `next dev`(NODE_ENV !== "production")에서는 별도 설정 없이 항상 켜진다(기존과 동일한 편의성).
// - Vercel 등 프로덕션 빌드(NODE_ENV === "production")에서는 기본적으로 꺼져 있다 — 비밀번호 없이
//   다른 계정 세션을 발급하는 기능이라, 아무 배포에나 기본으로 열려있으면 위험하기 때문이다.
// - 배포 환경에서도 빠른 테스트를 위해 계속 쓰고 싶다면, 그 배포의 환경변수에
//   NEXT_PUBLIC_ENABLE_DEV_TOOLS=true 를 명시적으로 설정해야만 켜진다(의도적 opt-in).
// 서버 라우트(dev-impersonate 등)와 클라이언트 컴포넌트(DevRoleToggle) 양쪽에서 이 함수 하나로
// 판단해야 기준이 갈라지지 않는다 — NEXT_PUBLIC_ 접두사라 서버/클라이언트 어디서든 읽을 수 있다.
export function isDevToolsEnabled(): boolean {
  if (process.env.NODE_ENV !== "production") return true;
  return process.env.NEXT_PUBLIC_ENABLE_DEV_TOOLS === "true";
}
