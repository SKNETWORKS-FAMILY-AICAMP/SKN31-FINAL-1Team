import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FullAutoPanel } from "./FullAutoPanel";
import { apiFetch } from "@/lib/api/client";
vi.mock("@/lib/api/client", () => ({ apiFetch: vi.fn() }));
const api = vi.mocked(apiFetch);
const job = (status: string) => ({ job: { id: "j1", status, stage: status, message: "인력 정보를 확인해주세요" } });
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });

describe("FullAutoPanel", () => {
  it("locks manual actions while pending and refreshes once on completion", async () => {
    vi.useFakeTimers();
    api.mockResolvedValueOnce(job("PENDING")).mockResolvedValueOnce(job("SUCCESS"));
    const done = vi.fn().mockResolvedValue(undefined);
    await act(async () => { render(<FullAutoPanel noteId={1} canView onCompleted={done}><button>수동 생성</button></FullAutoPanel>); });
    expect(screen.getByText("수동 생성")).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(screen.getByText("수동 생성")).toBeEnabled();
    expect(done).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(api).toHaveBeenCalledTimes(2);
  });

  it("shows failure and lets the owner requeue it", async () => {
    api.mockResolvedValueOnce(job("ERROR")).mockResolvedValueOnce({status: "PENDING"}).mockResolvedValue(job("PENDING"));
    await act(async () => { render(<FullAutoPanel noteId={2} canView onCompleted={vi.fn()}><button>수동 생성</button></FullAutoPanel>); });
    expect(screen.getByText("인력 정보를 확인해주세요")).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByText("실패한 단계부터 재시도")); });
    expect(api).toHaveBeenCalledWith("/api/meetings/notes/2/full-auto/", {method: "POST"});
    expect(screen.getByText("수동 생성")).toBeDisabled();
  });

  it("keeps manual meetings editable", async () => {
    api.mockResolvedValue({job: null});
    await act(async () => { render(<FullAutoPanel noteId={3} canView onCompleted={vi.fn()}><button>수동 생성</button></FullAutoPanel>); });
    expect(screen.getByText("수동 생성")).toBeEnabled();
    expect(screen.queryByText("자동 업무 배분")).not.toBeInTheDocument();
  });
});
