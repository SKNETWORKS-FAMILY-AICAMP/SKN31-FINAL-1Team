import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn/ui 표준 헬퍼: clsx로 조건부 className들을 하나로 합치고, twMerge로 뒤에 오는 값이
// 앞의 충돌되는 Tailwind 클래스(예: p-2와 p-4)를 덮어쓰도록 정리한다.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
