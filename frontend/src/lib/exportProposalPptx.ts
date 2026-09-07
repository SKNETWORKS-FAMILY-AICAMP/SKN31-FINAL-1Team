import type { ProposalDoc } from "@/lib/documentTemplates";

// FR-05-009: 기획서는 PPTX 형식으로 다운로드 가능해야 함
// ProposalDoc은 documentTemplates.ts에 정의된 단일 기획서 스키마이므로, AI가 채운 내용이든
// 사용자가 화면에서 수정한 내용이든 이 함수 하나로 항상 같은 슬라이드 레이아웃으로 내보낼 수 있다.
export async function exportProposalPptx(doc: ProposalDoc, title: string) {
  // pptxgenjs는 번들 크기가 커서 export 버튼을 눌렀을 때만 동적 import로 불러온다.
  const PptxGenJS = (await import("pptxgenjs")).default;
  const pptx = new PptxGenJS();
  // 기본 16:9 대신 가로 10in x 세로 5.63in의 커스텀 A4 비율 레이아웃을 사용 (화면 미리보기/인쇄 비율에 맞춤).
  pptx.defineLayout({ name: "A4", width: 10, height: 5.63 });
  pptx.layout = "A4";

  const TITLE_COLOR = "1E293B";
  const ACCENT = "2563EB";

  // Title slide
  const titleSlide = pptx.addSlide();
  titleSlide.addText(title, { x: 0.5, y: 2.1, w: 9, h: 1, fontSize: 32, bold: true, color: TITLE_COLOR });
  titleSlide.addText("프로젝트 기획서", { x: 0.5, y: 3.0, w: 9, h: 0.5, fontSize: 18, color: ACCENT });

  // "제목 + 본문 텍스트" 형태의 슬라이드가 여러 섹션(개요/문제정의/대상사용자/기술스택)에서
  // 반복되므로 매번 addSlide를 새로 쓰지 않고 헬퍼 함수로 묶어 재사용한다.
  const addSectionSlide = (heading: string, bodyText: string) => {
    const slide = pptx.addSlide();
    slide.addText(heading, { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
    slide.addText(bodyText || "-", { x: 0.5, y: 1.2, w: 9, h: 4, fontSize: 14, color: TITLE_COLOR, valign: "top" });
    return slide;
  };

  addSectionSlide("1. 프로젝트 개요", doc.projectOverview);
  addSectionSlide("2. 문제 정의", doc.problemDefinition);
  addSectionSlide("3. 대상 사용자", doc.target);
  addSectionSlide("4. 주요 기능", doc.features);
  addSectionSlide("5. 사용자 시나리오", doc.userScenario);
  addSectionSlide("6. 기술 스택 및 제약사항", doc.techStackConstraints);
  addSectionSlide("7. 최종 결정사항", doc.finalDecisions);

  await pptx.writeFile({ fileName: `${title}_기획서.pptx` });
}
