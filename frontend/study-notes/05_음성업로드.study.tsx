// ============================================================================
// 📘 학습용 사본 — 실제 앱에서 쓰이지 않습니다.
// 원본: src/components/projects/NewDocumentModal.tsx
// (원본에서 "음성 파일 업로드 → 진행률 게이지" 부분만 골라옴)
// ============================================================================

"use client";
import { useState, useRef } from "react";
import { apiFetch } from "@/lib/api/client";

type AudioStage = "transcribing" | "cleaning" | null;

// 각 단계가 0~100 중 어디부터 어디까지 채워질지 미리 정해둔 표.
// transcribing(음성 인식)은 5%에서 시작해 55%까지, cleaning(내용 정리)은
// 55%에서 95%까지 — 두 단계를 합쳐 전체 진행률처럼 보이게 만드는 트릭.
const STAGE_RANGE: Record<Exclude<AudioStage, null>, { from: number; to: number; label: string }> = {
  transcribing: { from: 5, to: 55, label: "음성 인식 중" },
  cleaning: { from: 55, to: 95, label: "내용 정리 중" },
};

export function NewDocumentModalExcerpt() {
  const [content, setContent] = useState("");
  const [uploadingFile, setUploadingFile] = useState(false);
  const [audioStage, setAudioStage] = useState<AudioStage>(null);
  const [audioProgress, setAudioProgress] = useState(0);   // 0~100
  const fileInputRef = useRef<HTMLInputElement>(null);
  // 💡 useRef — useState와 다르게, 값이 바뀌어도 화면을 다시 그리지 않는
  // "그냥 어떤 값을 담아두는 상자"다. 여기선 숨겨둔 <input type="file"> DOM
  // 요소 자체를 기억해서, 버튼을 눌렀을 때 그 input을 대신 클릭시키는 용도.

  // ---------------------------------------------------------------------
  // 💡 서버가 진행률(%)을 실시간으로 알려주지 않는다(요청 1번 보내고 응답 1번
  // 받는 구조라 중간 상태를 못 받음). 그래서 "그럴듯하게 채워지는 척"을 한다:
  // 0.35초마다 "남은 거리의 12%만큼"씩 다가가게 만들면, 처음엔 빠르게 움직이다가
  // 목표치 근처에서는 점점 느려지는(절대 도달하지 않는) 곡선이 만들어진다.
  // 실제 응답이 도착하면 setAudioProgress(range.to)로 그 단계의 목표치에 딱 맞춘다.
  // ---------------------------------------------------------------------
  const runAudioStage = async <T,>(
    stage: Exclude<AudioStage, null>,
    task: () => Promise<T>
  ): Promise<T> => {
    const range = STAGE_RANGE[stage];
    setAudioStage(stage);
    setAudioProgress(range.from);

    const interval = setInterval(() => {
      // 💡 setAudioProgress(p => ...) 처럼 "함수를 넘기는" 방식 —
      // "이전 값(p)을 받아서 새 값을 계산해라"는 뜻. setInterval 안에서는
      // 바깥의 audioProgress 변수를 그대로 쓰면 "그 시점에 고정된 옛날 값"만
      // 보게 되는 함정이 있어서(클로저 문제), 항상 최신값을 받는 이 방식을 쓴다.
      setAudioProgress(p => {
        const remaining = range.to - p;
        return remaining <= 1 ? p : p + Math.max(1, remaining * 0.12);
      });
    }, 350);

    try {
      const result = await task();       // 실제 서버 요청이 여기서 끝날 때까지 기다림
      setAudioProgress(range.to);         // 도착하자마자 목표치로 스냅
      return result;
    } finally {
      // 💡 성공하든 실패하든 반드시 실행되는 구역 — 타이머를 꼭 꺼줘야 한다.
      // 안 그러면 이 함수가 끝난 뒤에도 setInterval이 계속 남아서 계속 실행된다.
      clearInterval(interval);
    }
  };

  // ---------------------------------------------------------------------
  // 실제 파일 선택 이벤트 핸들러 — <input type="file" onChange={handleFileSelected}>
  // ---------------------------------------------------------------------
  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];   // 사용자가 고른 파일(여러 개 골라도 첫 번째만 씀)
    e.target.value = "";                 // 같은 파일을 다시 선택해도 onChange가 또 뜨도록 초기화
    if (!file) return;

    setUploadingFile(true);
    try {
      const formData = new FormData();   // 파일은 JSON으로 못 보내서 FormData라는 특수 형식을 씀
      formData.append("file", file);

      // 1/2단계: 서버에 파일을 보내서 Whisper로 받아쓰기
      const { transcript } = await runAudioStage("transcribing", () =>
        apiFetch<{ transcript: string }>("/api/meetings/notes/transcribe-audio/", {
          method: "POST",
          body: formData,
        })
      );

      // 2/2단계: 받아쓴 원문을 GPT에게 다시 보내서 필러 단어 제거 + 문장 정리
      // 💡 여기서 파일을 다시 안 보내고 "텍스트"만 보낸다 — 그래서 body가
      // FormData가 아니라 JSON.stringify(...)로 바뀐 것에 주목.
      const { content: cleaned } = await runAudioStage("cleaning", () =>
        apiFetch<{ content: string }>("/api/meetings/notes/cleanup-transcript/", {
          method: "POST",
          body: JSON.stringify({ text: transcript }),
        })
      );

      setContent(cleaned);   // "원본 내용" 텍스트박스에 최종 결과를 채움
    } catch (err: any) {
      console.error(err.message);
    } finally {
      setUploadingFile(false);
      setAudioStage(null);
      setAudioProgress(0);
    }
  };

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".mp3,.mp4,.wav,.m4a,.webm"
        onChange={handleFileSelected}
        style={{ display: "none" }}   // 진짜 <input>은 못생겨서 숨기고, 버튼으로 대신 클릭시킴
      />
      <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploadingFile}>
        {uploadingFile ? (audioStage ? `${STAGE_RANGE[audioStage].label}...` : "추출 중...") : "파일/음성에서 불러오기"}
      </button>

      {audioStage && (
        <div>
          <span>{STAGE_RANGE[audioStage].label} — {Math.round(audioProgress)}%</span>
          {/* 게이지 바: width를 audioProgress %로 그리는 게 전부다.
              audioProgress가 useState라서 값이 바뀔 때마다 이 div가 다시 그려지고,
              CSS transition 덕분에 부드럽게 움직이는 것처럼 보인다. */}
          <div style={{ height: 6, background: "#eee" }}>
            <div style={{ height: "100%", width: `${audioProgress}%`, background: "#3457D5", transition: "width .3s" }} />
          </div>
        </div>
      )}

      <textarea value={content} onChange={e => setContent(e.target.value)} />
    </div>
  );
}

// -----------------------------------------------------------------------------
// 🧪 스스로 확인해볼 것
// 1. runAudioStage 함수 이름 앞의 <T,> 는 뭘까? (03번 파일의 apiFetch<T>와 같은 개념)
//    → "이 함수가 다루는 값의 타입을 호출할 때마다 다르게 지정할 수 있다"는 뜻.
//      transcribing 단계에서는 T가 { transcript: string }, cleaning 단계에서는
//      { content: string }으로 서로 다르게 쓰인다.
// 2. setInterval의 콜백에서 setAudioProgress(p => ...) 대신
//    setAudioProgress(audioProgress + 1) 처럼 바깥 변수를 직접 쓰면 왜 문제일까?
//    → runAudioStage가 호출된 "그 순간"의 audioProgress 값이 고정되어(클로저),
//      실제로 게이지가 거의 안 움직이거나 이상하게 동작하게 된다. 실제로 이런
//      실수는 React에서 아주 흔한 버그 원인 중 하나다.
// -----------------------------------------------------------------------------
