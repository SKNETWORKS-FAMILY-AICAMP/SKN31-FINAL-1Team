import type { NextConfig } from "next";

// 2026-09-17: 프론트(vercel.app)와 백엔드(duckdns.org)가 서로 다른 도메인이라, 백엔드가
// 내려주는 쿠키(csrftoken/access_token 등)가 브라우저에는 "제3자 쿠키"로 보여 차단당했다
// (Safari/Firefox는 기본 차단, Chrome도 점점 같은 방향) — SameSite=None으로 바꿔도 애초에
// 저장 자체를 안 해줘서 소용없었다. 이 rewrite로 브라우저는 항상 프론트와 같은 도메인
// (heyzzabi-heyzzabi.vercel.app)에만 요청하게 하고, 실제 백엔드로의 중계는 Vercel 서버가
// 대신 해준다 — 그러면 쿠키가 "같은 도메인"에서 온 것으로 보여 정상 저장/전송된다.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // 2026-09-17: 프론트 코드가 이미 거의 모든 경로에 끝 슬래시를 붙여서 호출한다
        // (/api/users/login/ 등) — 여기서 또 붙이면 "login//"처럼 슬래시가 겹쳐 Django가
        // 404를 낸다(이 rewrite가 실제로 프로덕션에서 쓰인 적이 없어서 지금까지 안 드러났다).
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;