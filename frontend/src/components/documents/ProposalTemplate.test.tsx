import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ProposalTemplate } from "./ProposalTemplate";
import type { ProposalDoc } from "@/lib/documentTemplates";

const baseDoc: ProposalDoc = {
  projectOverview: "",
  problemDefinition: "",
  projectGoals: "",
  target: "",
  features: "",
  techStackConstraints: "",
  finalDecisions: "",
};

describe("ProposalTemplate (read mode)", () => {
  it("renders allowed HTML structure (subheadings/bullets) from backend content_html", () => {
    render(
      <ProposalTemplate
        doc={{
          ...baseDoc,
          features: "<p><strong>데이터 요구</strong></p><ul><li>최근 30일 검색 기록 활용</li></ul>",
        }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
      />
    );
    expect(screen.getByText("데이터 요구").tagName).toBe("STRONG");
    expect(screen.getByText("최근 30일 검색 기록 활용").closest("ul")).not.toBeNull();
  });

  // 회귀 테스트: 백엔드가 4개 허용 태그(p/strong/ul/li) 외의 태그나 이벤트 핸들러 속성을
  // 실수로 흘려보내도(또는 AI 출력이 오염돼도) 실제 DOM에는 스크립트가 심기지 않아야 한다.
  it("strips disallowed tags and event-handler attributes (XSS defense)", () => {
    render(
      <ProposalTemplate
        doc={{
          ...baseDoc,
          features: '<img src=x onerror="window.__pwned=true"><script>window.__pwned=true</script><p onclick="window.__pwned=true">hi</p>',
        }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
      />
    );
    expect(screen.getByText("hi").tagName).toBe("P");
    expect(screen.getByText("hi").getAttribute("onclick")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect((window as any).__pwned).toBeUndefined();
  });

  it("shows a placeholder dash for an empty section", () => {
    render(<ProposalTemplate doc={baseDoc} title="테스트 기획서" dateLabel="2026. 9. 7." />);
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });

  it("splits a legacy one-line numbered result into separate paragraphs while keeping numbers", () => {
    render(
      <ProposalTemplate
        doc={{ ...baseDoc, projectGoals: "(1) 첫 번째 목표 (2) 두 번째 목표 (3) 세 번째 목표" }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
      />
    );
    expect(screen.getByText("(1) 첫 번째 목표").tagName).toBe("P");
    expect(screen.getByText("(2) 두 번째 목표").tagName).toBe("P");
    expect(screen.getByText("(3) 세 번째 목표").tagName).toBe("P");
  });

  it("shows section evidence buttons and opens the selected section quotes", () => {
    const onViewEvidence = vi.fn();
    render(
      <ProposalTemplate
        doc={{ ...baseDoc, features: "<p><strong>예약 알림</strong></p>" }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        evidenceItems={{
          projectOverview: { quotes: ["문서 자동화가 필요합니다."] },
          features: {
            quotes: [],
            items: [
              { title: "예약 알림", quotes: ["예약 전날에도 알려주세요."] },
              { title: "복약 알림", quotes: ["복약 시간에 맞춰 알려주세요.", "보호자에게도 알려주세요."] },
            ],
          },
        }}
        onViewEvidence={onViewEvidence}
      />
    );

    expect(screen.getAllByRole("button", { name: /원문 보기/ })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "프로젝트 개요 원문 보기" })).toHaveTextContent("원문 보기 · 1");
    fireEvent.click(screen.getByRole("button", { name: "주요 기능 원문 보기" }));
    // 항목별 근거가 있는 섹션(주요 기능)은 색상 구분용 그룹(items)도 함께 넘긴다 —
    // EvidencePanel이 이 세 번째 인자로 항목별 하이라이트 색을 나눈다.
    expect(onViewEvidence).toHaveBeenCalledWith(
      "features",
      [
        "예약 전날에도 알려주세요.",
        "복약 시간에 맞춰 알려주세요.",
        "보호자에게도 알려주세요.",
      ],
      [
        { title: "예약 알림", quotes: ["예약 전날에도 알려주세요."] },
        { title: "복약 알림", quotes: ["복약 시간에 맞춰 알려주세요.", "보호자에게도 알려주세요."] },
      ],
    );
  });

  it("does not show an evidence button for a section without verified quotes", () => {
    render(
      <ProposalTemplate
        doc={{ ...baseDoc, techStackConstraints: "회의에서 논의되지 않았습니다." }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        evidenceItems={{ techStackConstraints: { quotes: [] } }}
        onViewEvidence={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: "기술 스택 및 제약사항 원문 보기" })).not.toBeInTheDocument();
  });
});
