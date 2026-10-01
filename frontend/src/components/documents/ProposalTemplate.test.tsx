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

  const featuresDoc = {
    ...baseDoc,
    features: "<p><strong>예약 알림</strong></p><p>전날 알림을 보낸다.</p><p><strong>복약 알림</strong></p><p>정해진 시간에 알린다.</p>",
  };
  const featuresEvidence = {
    features: {
      quotes: [],
      items: [
        { title: "예약 알림", quotes: ["예약 전날에도 알려주세요."] },
        { title: "복약 알림", quotes: ["복약 시간에 맞춰 알려주세요."] },
      ],
    },
  };

  it("does not highlight features before the evidence panel for that section is opened", () => {
    render(
      <ProposalTemplate
        doc={featuresDoc}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        evidenceItems={featuresEvidence}
        // activeEvidenceKey를 아예 안 주거나 다른 섹션을 가리키면 "원문 보기"를
        // 아직 안 누른 상태와 같다 — 이때는 색이 보이면 안 된다.
      />
    );

    expect(screen.getByText("예약 알림")).toBeInTheDocument();
    expect(document.querySelector(".bg-amber-100")).toBeNull();
    expect(document.querySelector(".bg-sky-100")).toBeNull();
  });

  it("highlights each feature with a different background color once its evidence panel is active", () => {
    render(
      <ProposalTemplate
        doc={featuresDoc}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        evidenceItems={featuresEvidence}
        activeEvidenceKey="features"
      />
    );

    const reservationBlock = screen.getByText("예약 알림").closest("div.rounded-lg");
    const medicationBlock = screen.getByText("복약 알림").closest("div.rounded-lg");
    expect(reservationBlock).not.toBeNull();
    expect(medicationBlock).not.toBeNull();
    // 서로 다른 기능은 서로 다른 배경색을 써야 한다(근거 패널과 같은 팔레트·순서).
    expect(reservationBlock!.className).not.toBe(medicationBlock!.className);
    expect(reservationBlock!.className).toContain("bg-amber-100");
    expect(medicationBlock!.className).toContain("bg-sky-100");
  });

  it("falls back to plain rendering for features without per-item evidence even when active", () => {
    render(
      <ProposalTemplate
        doc={{ ...baseDoc, features: "<p><strong>예약 알림</strong></p><p>전날 알림을 보낸다.</p>" }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        activeEvidenceKey="features"
      />
    );

    expect(screen.getByText("예약 알림")).toBeInTheDocument();
    expect(document.querySelector("div.rounded-lg")).toBeNull();
  });

  it("hides the PM 확인 사항 block from a plain section in read mode", () => {
    render(
      <ProposalTemplate
        doc={{
          ...baseDoc,
          techStackConstraints:
            "<p>React와 Node.js를 사용한다.</p><p><strong>PM 확인 사항</strong></p><ul><li>인증 방식을 확정해 주세요.</li></ul>",
        }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
      />
    );

    expect(screen.getByText("React와 Node.js를 사용한다.")).toBeInTheDocument();
    expect(screen.queryByText("PM 확인 사항")).not.toBeInTheDocument();
    expect(screen.queryByText("인증 방식을 확정해 주세요.")).not.toBeInTheDocument();
  });

  it("hides the PM 확인 사항 block from the colored feature list too", () => {
    render(
      <ProposalTemplate
        doc={{
          ...baseDoc,
          features:
            "<p><strong>예약 알림</strong></p><p>전날 알림을 보낸다.</p><p><strong>PM 확인 사항</strong></p><ul><li>알림 시각을 확정해 주세요.</li></ul>",
        }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        evidenceItems={{ features: { quotes: [], items: [{ title: "예약 알림", quotes: ["예약 전날에도 알려주세요."] }] } }}
        activeEvidenceKey="features"
      />
    );

    expect(screen.getByText("예약 알림")).toBeInTheDocument();
    expect(screen.queryByText("PM 확인 사항")).not.toBeInTheDocument();
    expect(screen.queryByText("알림 시각을 확정해 주세요.")).not.toBeInTheDocument();
  });

  it("still shows the PM 확인 사항 block while directly editing (직접 수정 모드)", () => {
    render(
      <ProposalTemplate
        doc={{
          ...baseDoc,
          techStackConstraints:
            "<p>React와 Node.js를 사용한다.</p><p><strong>PM 확인 사항</strong></p><ul><li>인증 방식을 확정해 주세요.</li></ul>",
        }}
        title="테스트 기획서"
        dateLabel="2026. 9. 7."
        editable
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText("PM 확인 사항")).toBeInTheDocument();
    expect(screen.getByText("인증 방식을 확정해 주세요.")).toBeInTheDocument();
  });
});
