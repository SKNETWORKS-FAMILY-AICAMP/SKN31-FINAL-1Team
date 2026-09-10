// ============================================================================
// 📘 학습용 사본 — 실제 앱에서 쓰이지 않습니다.
// 원본: src/app/(dashboard)/documents/page.tsx (2700줄 이상 되는 거대 파일)
//
// ⚠️ 이건 원본 전체가 아니라, "데이터를 어떻게 가져오고 화면에 반영하는지"에
// 해당하는 핵심 부분만 골라서 뽑아온 것입니다. 원본 파일을 열어서 같은 함수
// 이름(fetchAll, selectNote 등)을 검색해보면서 앞뒤 맥락을 같이 보세요.
// ============================================================================

"use client";
import { useState, useEffect, useMemo } from "react";
import { apiFetch } from "@/lib/api/client";

// 서버가 주는 회의록 하나의 모양(일부만) — 실제로는 더 많은 필드가 있음
type NoteDto = {
  id: number;
  title: string;
  updated_at: string;
  spec_documents: any[]; // 이 회의록에서 파생된 기획서 목록
  project: number | null;
};

export default function DocumentsPage() {
  // ---------------------------------------------------------------------
  // 이 화면이 "기억해야 하는 것"들 — 전부 useState.
  // 서버에서 아무것도 안 받아온 시작 시점엔 빈 배열/null로 시작한다.
  // ---------------------------------------------------------------------
  const [project, setProject] = useState<{ id: number; name: string } | null>(null);
  const [notes, setNotes] = useState<NoteDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);

  // ---------------------------------------------------------------------
  // fetchAll — "서버한테 가서 최신 데이터 다 받아와서 창고에 넣기"
  // 화면이 처음 열릴 때뿐 아니라, 새 회의록을 만들고 난 뒤에도 다시 부른다
  // (그래서 이름이 "handleXxx"가 아니라 그냥 재사용 가능한 함수로 따로 빼져 있음)
  // ---------------------------------------------------------------------
  const fetchAll = async (preferredProjectId?: number) => {
    setLoading(true);
    try {
      // 1. 프로젝트 목록을 받아온다. 이 앱은 "단일 프로젝트 운영 전제"라
      //    항상 목록의 첫 번째(또는 방금 만든 프로젝트)를 그냥 쓴다.
      const projects = await apiFetch<{ id: number; name: string }[]>("/api/projects/");
      const current = preferredProjectId
        ? projects.find(p => p.id === preferredProjectId) ?? projects[0]
        : projects[0];
      setProject(current ?? null);

      if (current) {
        // 2. 그 프로젝트에 속한 회의록 목록을 받아온다.
        //    💡 Promise.all([...])은 "여러 개의 비동기 작업을 동시에 시작해서,
        //    전부 끝날 때까지 같이 기다리기" — 순서대로 하나씩 await 하는 것보다 빠르다.
        const [noteList] = await Promise.all([
          apiFetch<NoteDto[]>(`/api/meetings/notes/?project=${current.id}`),
        ]);
        setNotes(noteList);  // ← 이 한 줄이 실행되는 순간, 이 컴포넌트가 다시 그려진다
      }
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false); // 성공하든 실패하든 "로딩 끝" 표시는 반드시 함
    }
  };

  // 💡 컴포넌트가 화면에 처음 나타났을 때 딱 한 번, fetchAll을 실행한다.
  useEffect(() => { fetchAll(); }, []);

  // ---------------------------------------------------------------------
  // 💡 useMemo — "이 값을 매번 다시 계산하지 말고, notes가 안 바뀌었으면 저번에
  // 계산해둔 걸 재사용해라"는 뜻. 정렬(sort)처럼 매번 다시 하면 낭비인 계산을
  // 캐싱해두는 용도다. useState와는 다르다 — 이 값 자체를 "기억"하는 게 아니라
  // "재계산을 건너뛰기 위한 캐시"다.
  // ---------------------------------------------------------------------
  const sortedNotes = useMemo(
    () => notes.slice().sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
    [notes]   // notes가 바뀔 때만 다시 정렬. 안 바뀌면 이전 정렬 결과 그대로 재사용
  );

  const selectedNote = useMemo(
    () => sortedNotes.find(n => n.id === selectedNoteId) ?? sortedNotes[0] ?? null,
    [sortedNotes, selectedNoteId]
  );

  // 사용자가 사이드바에서 회의록 하나를 클릭했을 때
  const selectNote = (note: NoteDto) => {
    setSelectedNoteId(note.id);
    // (원본에는 이 다음에 "이 문서가 지금 파이프라인의 어느 단계인지" 계산해서
    //  그 탭을 자동으로 열어주는 로직이 더 있음 — documentPipeline.ts 참고)
  };

  if (loading) {
    return <div>로딩 중...</div>;
  }

  return (
    <div>
      {/* 사이드바: sortedNotes를 하나씩 그린다 */}
      <div>
        {sortedNotes.map(note => (
          <button key={note.id} onClick={() => selectNote(note)}>
            {note.title}
          </button>
        ))}
      </div>

      {/* 오른쪽: 선택된 회의록의 상세 내용 (실제로는 별도 컴포넌트 NoteDetail로 분리됨) */}
      <div>
        {selectedNote ? selectedNote.title : "왼쪽에서 문서를 선택하세요"}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// 🧪 스스로 확인해볼 것
// 1. notes 배열 안의 순서를 직접 바꾸지 않고 sortedNotes라는 "새 배열"을 따로
//    만드는 이유는? (원본에 힌트: notes.slice().sort(...) — slice()가 왜 있을까?)
//    → .sort()는 원본 배열을 그 자리에서 바로 바꿔버린다(mutate). notes 자체를
//      바꾸면 useState가 "값이 바뀐 걸" 제대로 못 감지할 수 있어서, slice()로
//      복사본을 먼저 만들고 그 복사본을 정렬한다.
// 2. fetchAll이 async 함수인데 useEffect(() => { fetchAll(); }, [])처럼 그냥
//    호출만 하고 await를 안 붙인 이유는?
//    → useEffect에 넘기는 함수 자체는 Promise를 반환하면 안 된다는 React의 규칙이
//      있어서, 안에서 별도 async 함수를 만들어 호출만 하는 패턴을 쓴다.
// -----------------------------------------------------------------------------
