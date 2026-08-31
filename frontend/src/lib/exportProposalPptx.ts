import { stripLeadingNumber, type ProposalDoc } from "@/lib/documentTemplates";

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

  const featureSlide = pptx.addSlide();
  featureSlide.addText("4. 주요 기능", { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
  // pptxgenjs의 rich-text 배열: 기능명은 글머리 기호(bullet)로, 설명은 한 단계 들여쓰기(indentLevel)해서
  // "기능명 - 설명" 구조가 한눈에 보이도록 구성한다.
  const PRIORITY_COLOR: Record<string, string> = { 필수: "DC2626", 권장: "2563EB", 선택: "94A3B8" };
  const featureBullets = (doc.features || []).flatMap(f => ([
    {
      text: `${f.name}  [${f.priority ?? "권장"}]`,
      options: { bold: true, fontSize: 14, color: PRIORITY_COLOR[f.priority ?? "권장"] ?? TITLE_COLOR, bullet: true, breakLine: true },
    },
    { text: f.description, options: { fontSize: 11, color: "64748B", indentLevel: 1, breakLine: true } },
  ]));
  featureSlide.addText(featureBullets.length ? featureBullets : [{ text: "-" }], { x: 0.5, y: 1.2, w: 9, h: 4, valign: "top" });

  // 저장된 문자열엔 번호가 없으므로(화면의 <ol>이 번호를 매기는 것과 동일한 이유로 여기서도
  // stripLeadingNumber로 혹시 남아있을 옛 번호를 벗겨낸 뒤) 슬라이드에서 직접 번호를 매긴다.
  if (doc.userScenario?.length) {
    const scenarioSlide = pptx.addSlide();
    scenarioSlide.addText("5. 사용자 시나리오", { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
    const scenarioBullets = doc.userScenario.map((step, i) => ({
      text: `${i + 1}. ${stripLeadingNumber(step)}`,
      options: { fontSize: 13, color: TITLE_COLOR, breakLine: true, paraSpaceAfter: 6 },
    }));
    scenarioSlide.addText(scenarioBullets, { x: 0.5, y: 1.2, w: 9, h: 4, valign: "top" });
  }

  addSectionSlide("6. 기술 스택 및 제약사항", doc.techStackConstraints);

  if (doc.finalDecisions?.length) {
    const decisionSlide = pptx.addSlide();
    decisionSlide.addText("7. 최종 결정사항", { x: 0.5, y: 0.4, w: 9, h: 0.6, fontSize: 24, bold: true, color: ACCENT });
    const decisionBullets = doc.finalDecisions.map(d => ({
      text: d,
      options: { fontSize: 13, color: TITLE_COLOR, bullet: true, breakLine: true, paraSpaceAfter: 6 },
    }));
    decisionSlide.addText(decisionBullets, { x: 0.5, y: 1.2, w: 9, h: 4, valign: "top" });
  }

  await pptx.writeFile({ fileName: `${title}_기획서.pptx` });
}
