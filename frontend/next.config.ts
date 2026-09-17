import type { NextConfig } from "next";

// 2026-09-17: /api/* 프록시는 rewrites()가 아니라 src/app/api/[...path]/route.ts에서
// 직접 처리한다 — rewrites()는 목적지가 빌드 시점에 고정되고, 외부 도메인 + 캐치올 조합에서
// 자기 자신으로 리다이렉트되는 문제가 있었다(Turbopack 이슈로 추정). skipTrailingSlashRedirect는
// 그 route handler가 끝 슬래시가 붙은 경로(/api/users/login/ 등)를 원본 그대로 받도록 유지한다.
const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
