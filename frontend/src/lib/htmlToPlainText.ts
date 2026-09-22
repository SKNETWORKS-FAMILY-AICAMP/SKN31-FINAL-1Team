// 2026-09-22(사용자 요청): "PM 확인 사항"은 완성된 기획서를 읽는 화면·문서에는
// 안 보여준다 — 원문 대조로 확인할 수 있고 PM이 어차피 전체 검수를 하므로 굳이
// 넣지 않아도 된다는 판단. ProposalTemplate.tsx(화면)와 exportProposalPptx.ts
// (PPTX)가 이 함수 하나를 같이 써서, 화면에서 지운 걸 PPTX에서 깜빡 빠뜨리는
// 일이 없게 한다. "직접 수정" 모드는 원본을 그대로 보여줘야 하므로 이 함수를
// 거치지 않는다(ProposalTemplate.tsx의 EditableRichText 참고).
export function stripPmReviewNotes(html: string): string {
  if (!html) return html;
  return html.replace(/<p><strong>PM 확인 사항<\/strong><\/p><ul>[\s\S]*?<\/ul>\s*$/i, "").trim();
}

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
