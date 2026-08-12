// LLM 응답에서 JSON을 최대한 관대하게 뽑아낸다 — 모델이 ```json 코드펜스나
// 앞뒤 설명을 덧붙여도 파싱을 시도한다. Claude/OpenAI 프로바이더가 공유해서 쓴다.
export function parseJsonLoose<T>(text: string): T | null {
  let s = text.trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1]!.trim();
  try {
    return JSON.parse(s) as T;
  } catch {
    const first = Math.min(...[s.indexOf("["), s.indexOf("{")].filter((i) => i >= 0));
    const last = Math.max(s.lastIndexOf("]"), s.lastIndexOf("}"));
    if (Number.isFinite(first) && last > first) {
      try {
        return JSON.parse(s.slice(first, last + 1)) as T;
      } catch {
        return null;
      }
    }
    return null;
  }
}
