import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
