import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidencePanel } from "./EvidencePanel";

describe("EvidencePanel", () => {
  it("shows the full transcript and highlights every exact matching quote", () => {
    render(
      <EvidencePanel
        open
        onClose={() => undefined}
        fullText={"앞 문맥입니다. 근거 문장입니다. 뒤 문맥입니다. 근거 문장입니다."}
        targetQuotes={["근거 문장입니다."]}
      />
    );

    expect(screen.getByText(/앞 문맥입니다/)).toBeInTheDocument();
    expect(screen.getByText(/뒤 문맥입니다/)).toBeInTheDocument();
    expect(document.querySelectorAll("mark")).toHaveLength(2);
  });

  it("keeps the full transcript visible when a quote cannot be found", () => {
    render(<EvidencePanel open onClose={() => undefined} fullText="전체 회의록" targetQuotes={["없는 문장"]} />);
    expect(screen.getByText("전체 회의록")).toBeInTheDocument();
    expect(document.querySelector("mark")).toBeNull();
  });

  it("closes from the close button and overlay", () => {
    const onClose = vi.fn();
    render(<EvidencePanel open onClose={onClose} fullText="회의록" targetQuotes={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    fireEvent.click(screen.getByRole("button", { name: "원문 패널 닫기" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("adjusts the desktop panel width with the keyboard", () => {
    const onWidthChange = vi.fn();
    render(
      <EvidencePanel
        open
        onClose={() => undefined}
        fullText="회의록"
        targetQuotes={["회의록"]}
        width={560}
        onWidthChange={onWidthChange}
      />
    );
    fireEvent.keyDown(screen.getByRole("separator", { name: "원문 패널 너비 조절" }), { key: "ArrowLeft" });
    expect(onWidthChange).toHaveBeenCalledWith(584);
  });

  it("colors each group's quotes differently and shows a legend when targetGroups is given", () => {
    render(
      <EvidencePanel
        open
        onClose={() => undefined}
        fullText={"예약 전날에도 알려주세요. 복약 시간에 맞춰 알려주세요."}
        targetQuotes={[]}
        targetGroups={[
          { title: "예약 알림", quotes: ["예약 전날에도 알려주세요."] },
          { title: "복약 알림", quotes: ["복약 시간에 맞춰 알려주세요."] },
        ]}
      />
    );

    // 범례에 항목 제목이 보여야 한다.
    expect(screen.getByText("예약 알림")).toBeInTheDocument();
    expect(screen.getByText("복약 알림")).toBeInTheDocument();

    const marks = document.querySelectorAll("mark");
    expect(marks).toHaveLength(2);
    // 서로 다른 그룹이므로 하이라이트 배경색 클래스가 달라야 한다.
    expect(marks[0].className).not.toBe(marks[1].className);
    expect(marks[0].getAttribute("data-group-index")).toBe("0");
    expect(marks[1].getAttribute("data-group-index")).toBe("1");
  });

  it("falls back to the single-color highlight when targetGroups is not given", () => {
    render(
      <EvidencePanel
        open
        onClose={() => undefined}
        fullText="근거 문장입니다."
        targetQuotes={["근거 문장입니다."]}
      />
    );

    // 항목 없는 섹션(기존 동작)은 범례가 없고 기존 amber 하이라이트를 그대로 쓴다.
    expect(screen.queryByText("예약 알림")).not.toBeInTheDocument();
    const mark = document.querySelector("mark");
    expect(mark).not.toBeNull();
    expect(mark!.className).toContain("bg-amber-200");
  });
});
