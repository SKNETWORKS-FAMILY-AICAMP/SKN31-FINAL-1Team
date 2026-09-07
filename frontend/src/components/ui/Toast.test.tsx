import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Toast } from "./Toast";

describe("Toast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when message is null", () => {
    const { container } = render(<Toast message={null} onDismiss={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the message and auto-dismisses after the default duration", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<Toast message="저장되었습니다" onDismiss={onDismiss} />);
    expect(screen.getByText("저장되었습니다")).toBeInTheDocument();

    vi.advanceTimersByTime(2199);
    expect(onDismiss).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  // alert()->Toast 통일 작업으로 추가된 variant="error"가 성공 토스트보다 더 오래
  // 떠 있어야 한다는 요구사항(실패 메시지는 읽을 시간이 더 필요함)을 지키는지 확인한다.
  it("stays visible longer for the error variant than the default success variant", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<Toast message="실패했습니다" variant="error" onDismiss={onDismiss} />);

    vi.advanceTimersByTime(2200);
    expect(onDismiss).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1000);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
