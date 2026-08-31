import type { User } from "@/lib/auth";

// GET /api/users/me/ (UserDetailSerializer) 응답 전용 — role_info.code_id가 USER_ROLE 공통
// 코드(ADMIN/TEAM_LEAD/EMPLOYEE, backend/common/management/commands/seed_codes.py 참고) 중
// 하나로 온다. 이 프론트는 PM/MEMBER 이분법만 알아서, "관리자(ADMIN)"만 PM으로 매핑하고
// 나머지(TEAM_LEAD/EMPLOYEE)는 전부 MEMBER로 묶는다 — TEAM_LEAD를 PM 권한으로 볼지는
// 백엔드/기획 쪽과 확인 필요(2026-08-31 기준 가정).
//
// 2026-08-31: 기존 시드 계정들(예: "pm")은 role_code가 아직 비어있고(None), 실제 PM 권한
// 판단은 지금 Django의 is_staff 플래그로만 되고 있었다(users/permissions.py의
// IsAdminUserOnly도 is_staff 기준) — role_code가 다 채워지기 전까지는 is_staff도 함께 봐야
// "pm" 계정이 화면에서 일반 멤버로 잘못 보이지 않는다.
export function toUser(dto: any): User {
  return {
    id: String(dto.id),
    email: dto.username || "",
    name: dto.first_name || dto.last_name ? `${dto.last_name ?? ""}${dto.first_name ?? ""}` : (dto.full_name || dto.username || ""),
    role: dto.role_info?.code_id === "ADMIN" || dto.is_staff ? "PM" : "MEMBER",
    isFirstLogin: false,
  };
}
