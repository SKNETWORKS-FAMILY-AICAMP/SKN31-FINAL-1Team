// ProposalDoc의 각 섹션(overview/features/...)은 리치텍스트 에디터가 만든 HTML
// 문자열이다 — 화면에서는 dangerouslySetInnerHTML로 렌더링되지만, PPTX 등 순수
// 텍스트만 받는 곳에 그대로 넣으면 <p>, <br> 같은 태그가 글자 그대로 보인다.
// 블록 태그를 줄바꿈으로 바꾼 뒤 나머지 태그를 제거하고 엔티티를 복원한다.
export function htmlToPlainText(html: string): string {
  if (!html) return "";
  return html
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6])\s*\/?>/gi, "\n")
    .replace(/<li[^>]*>/gi, "- ")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
