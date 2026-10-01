"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// 화면마다 useEffect+useState로 손으로 캐싱/재요청을 짜던 걸 TanStack Query로 대체하기
// 위한 전역 Provider. staleTime을 넉넉히 잡아서(30초) "화면 나갔다 들어오면 또 로딩
// 스피너부터" 문제를 없앤다 — 그 안에서는 캐시를 그대로 보여주고, 지나면 백그라운드에서
// 조용히 갱신한다(화면이 깜빡이지 않음).
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
