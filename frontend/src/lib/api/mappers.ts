export function toUser(dto: any): User {
  return {
    id: String(dto.id),
    email: dto.username || "",
    name: dto.full_name || dto.username || "",
    role: dto.is_staff || dto.is_superuser ? "PM" : "MEMBER", // 권한 판단 조건에 맞춰 수정
    isFirstLogin: false,
  };
}