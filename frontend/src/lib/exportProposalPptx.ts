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

  // "제목 + 본문 텍스트" 형태의 슬라이드가 여러 섹션(배경/타겟/기대효과)에서 반복되므로
  // 매번 addSlide를 새로 쓰지 않고 헬퍼 함수로 묶어 재사용한다.
  const addSectionSlide = (heading: string, bodyText: string) => {
    const slide = pptx.addSlide();
    slide.addText(heading, { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
    slide.addText(bodyText || "-", { x: 0.5, y: 1.2, w: 9, h: 4, fontSize: 14, color: TITLE_COLOR, valign: "top" });
    return slide;
  };

  addSectionSlide("1. 배경 및 목적", doc.background);
  addSectionSlide("2. 타겟 사용자", doc.target);

  const featureSlide = pptx.addSlide();
  featureSlide.addText("3. 주요 기능", { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
  const featureLines = (doc.features || []).map(f => ({
    text: `${f.name}\n`,
    options: { bold: true, fontSize: 14, color: TITLE_COLOR, breakLine: false },
  }));
  // pptxgenjs의 rich-text 배열: 기능명은 글머리 기호(bullet)로, 설명은 한 단계 들여쓰기(indentLevel)해서
  // "기능명 - 설명" 구조가 한눈에 보이도록 구성한다.
  const featureBullets = (doc.features || []).flatMap(f => ([
    { text: f.name, options: { bold: true, fontSize: 14, color: TITLE_COLOR, bullet: true, breakLine: true } },
    { text: f.description, options: { fontSize: 11, color: "64748B", indentLevel: 1, breakLine: true } },
  ]));
  featureSlide.addText(featureBullets.length ? featureBullets : [{ text: "-" }], { x: 0.5, y: 1.2, w: 9, h: 4, valign: "top" });

  addSectionSlide("4. 기대 효과", doc.expectedEffect);

  // 원본 회의록/메모에 일정 언급이 없으면 milestones가 빈 배열이므로 이 슬라이드 자체를 생략한다
  // (없는 일정을 억지로 만들어 보여주지 않기 위함).
  if (doc.milestones?.length) {
    const msSlide = pptx.addSlide();
    msSlide.addText("5. 일정 / 마일스톤", { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
    const rows: any[] = [
      [{ text: "마일스톤", options: { bold: true, fill: { color: "F1F5F9" } } }, { text: "시기", options: { bold: true, fill: { color: "F1F5F9" } } }],
      ...doc.milestones.map(m => [m.name, m.date]),
    ];
    msSlide.addTable(rows, { x: 0.5, y: 1.2, w: 9, fontSize: 12, color: TITLE_COLOR, border: { type: "solid", color: "E2E8F0", pt: 1 } });
  }

  await pptx.writeFile({ fileName: `${title}_기획서.pptx` });
}
