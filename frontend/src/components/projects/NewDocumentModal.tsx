"use client";

import { useState, useEffect } from "react";
import { X, Loader2, FileText, Users, CalendarIcon, FolderKanban } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

type ProjectOption = { id: number; name: string };
const NEW_PROJECT_VALUE = "__new__";

// 2026-08-31: Django 백엔드(MeetingNote)로 재배선하면서 파일 첨부(.docx/.pdf/.hwp 텍스트 추출)는
// 뺐다 — heyzzabi2에는 /api/documents/parse-file 로컬 라우트가 있었지만 Django엔 대응 API가
// 없다. 직접 입력만 지원한다(범위 밖 — 필요해지면 별도로 구현).
const SAMPLE_NOTES = [
  `[신규 쇼핑몰 프로젝트 킥오프 회의록]
일자: 2026-08-19
참석자: PM, 개발팀장, 디자인팀장, 마케팅팀장

1. 배경 및 문제의식
- 기존 자사몰 앱은 출시 3년 차로 최근 6개월간 재방문율이 전년 대비 18% 하락했고, 특히 야간 시간대(21시~02시) 이탈률이 높다는 데이터가 있음.
- 신규 회원가입 단계에서 이탈이 큰데, 설문 결과 "이메일 회원가입 절차가 번거롭다"는 응답이 가장 많았음.

2. 결정 사항
- 다크모드: 시스템 설정 연동 + 앱 내 수동 전환 스위치 둘 다 지원.
- 소셜 로그인: 카카오·구글·네이버 3개사 우선 지원.
- AI 상품 추천: 최근 30일 검색 기록 + 장바구니 데이터를 기반으로 메인 화면 하단에 노출.

3. 다음 액션
- 디자인팀: 8/26까지 다크모드 시안 1차 초안 공유.
- 개발팀: 8/28 소셜 로그인 3사 API 키 발급 신청.`,

  `[내부 인트라넷 인사관리 기능 추가 회의록]
일자: 2026-08-20
참석자: 인사팀장, IT지원팀, 총무팀 담당자

1. 배경 및 목적
- 현재 '연차 휴가 신청'과 '출장 보고서'를 엑셀과 이메일로 관리하고 있는데, 인사팀 기준 월평균 40건 이상의 신청을 수기로 취합하다 보니 누락·중복 승인 사고가 최근 2건 발생함.

2. 연차 신청 기능 상세
- 달력 UI에서 시작일/종료일 선택. 주말·공휴일은 자동으로 신청 대상에서 제외.
- 반차(오전/오후) 선택 옵션 제공.
- 신청 즉시 담당 팀장에게 사내 메신저 + 이메일 동시 알림 발송.

3. 결정 사항
- 연차 신청은 반차(오전/오후) 옵션까지 포함해 이번 스코프에 반드시 넣기로 확정함.
- 출장 보고서 영수증 첨부는 이미지 파일 다중 첨부까지만 지원.`,
];

export function NewDocumentModal({
  defaultProjectId,
  onClose,
}: {
  // 문서생성 페이지가 현재 보고 있는 프로젝트가 있으면 기본 선택값으로 넘겨준다
  defaultProjectId?: number;
  onClose: (projectId?: number, createdNoteId?: number) => void;
}) {
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState("");
  const [attendees, setAttendees] = useState<string[]>([]);
  const [memberNames, setMemberNames] = useState<string[]>([]);
  const [content, setContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(defaultProjectId ? String(defaultProjectId) : "");
  const [newProjectName, setNewProjectName] = useState("");

  useEffect(() => {
    apiFetch<ProjectOption[]>("/api/projects/")
      .then(list => {
        setProjects(list);
        if (!defaultProjectId) {
          setSelectedProjectId(list.length > 0 ? String(list[0].id) : NEW_PROJECT_VALUE);
        }
      })
      .catch(() => setSelectedProjectId(NEW_PROJECT_VALUE))
      .finally(() => setLoadingProjects(false));
  }, [defaultProjectId]);

  // 참석자 드롭박스 후보 — DB에 등록된 사람 이름. 목록에 없는 사람은 TagAutocomplete에서 직접 입력해 추가할 수 있다.
  useEffect(() => {
    apiFetch<any[]>("/api/users/?simple=true")
      .then(list => setMemberNames(list.map((u: any) => u.full_name || u.username).filter(Boolean)))
      .catch(() => {});
  }, []);

  const deriveTitleFromContent = (text: string) => {
    const firstLine = text.split("\n").map(l => l.trim()).find(l => l.length > 0) ?? "";
    const bracketMatch = firstLine.match(/^\[(.+)\]$/);
    const base = (bracketMatch ? bracketMatch[1] : firstLine).slice(0, 40);
    return base || `새 문서 ${new Date().toLocaleTimeString()}`;
  };

  const extractMeetingDate = (text: string): string | null => {
    const keywordLine = text.split("\n").find(l => /(일자|날짜|회의일시|작성일)/.test(l));
    const searchIn = keywordLine ?? text;
    const isoMatch = searchIn.match(/(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})/);
    if (isoMatch) {
      const [, y, m, d] = isoMatch;
      if (Number(m) >= 1 && Number(m) <= 12 && Number(d) >= 1 && Number(d) <= 31) {
        return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
      }
    }
    const korMatch = searchIn.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/);
    if (korMatch) {
      const [, y, m, d] = korMatch;
      return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
    }
    return null;
  };

  useEffect(() => {
    if (!content.trim()) return;
    const timer = setTimeout(() => {
      setMeetingDate(prev => prev || extractMeetingDate(content) || "");
      if (memberNames.length > 0) {
        const found = memberNames.filter(name => content.includes(name));
        if (found.length > 0) {
          setAttendees(prev => Array.from(new Set([...prev, ...found])));
        }
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [content, memberNames]);

  const handleLoadSample = () => {
    const randomIndex = Math.floor(Math.random() * SAMPLE_NOTES.length);
    const sample = SAMPLE_NOTES[randomIndex];
    setContent(sample);
    if (!title.trim()) setTitle(deriveTitleFromContent(sample));
  };

  const isCreatingNewProject = selectedProjectId === NEW_PROJECT_VALUE;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!content.trim()) return;
    if (isCreatingNewProject && !newProjectName.trim()) return;

    const finalTitle = title.trim() || deriveTitleFromContent(content);

    setIsLoading(true);
    try {
      let targetProjectId = Number(selectedProjectId);

      if (isCreatingNewProject) {
        const newProject = await apiFetch<ProjectOption>("/api/projects/", {
          method: "POST",
          body: JSON.stringify({ name: newProjectName.trim() }),
        });
        targetProjectId = newProject.id;
      }

      const note = await apiFetch<any>("/api/meetings/notes/", {
        method: "POST",
        body: JSON.stringify({
          project: targetProjectId,
          title: finalTitle,
          content,
          meeting_date: meetingDate || null,
          attendees: attendees.length > 0 ? attendees.join(", ") : null,
        }),
      });

      onClose(targetProjectId, note.id);
    } catch (err: any) {
      setError(err.message || "문서 생성 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-3xl border border-border flex flex-col max-h-[95vh]">
        <div className="flex justify-between items-center p-5 border-b border-border shrink-0">
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="w-6 h-6 text-primary" />
              새 회의록 / 문서
            </h2>
            <p className="text-muted-foreground text-sm mt-1">회의 내용을 자유롭게 작성하세요.</p>
          </div>
          <button
            onClick={() => onClose()}
            className="text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5 p-2 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 flex-1 overflow-y-auto space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 text-red-500 text-sm">{error}</div>
          )}

          <form id="doc-form" onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-[3fr_2fr] gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">문서 제목 (선택)</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="비워두면 내용에서 자동으로 생성됩니다"
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 font-medium"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><FolderKanban className="w-3.5 h-3.5" /> 프로젝트</label>
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  disabled={loadingProjects}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm disabled:opacity-60"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                  <option value={NEW_PROJECT_VALUE}>+ 새 프로젝트</option>
                </select>
              </div>
            </div>

            {isCreatingNewProject && (
              <div>
                <label className="block text-sm font-medium mb-1">새 프로젝트 이름</label>
                <input
                  type="text"
                  required
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="예: 사내 인트라넷 고도화"
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><CalendarIcon className="w-3.5 h-3.5" /> 회의 일시 (선택)</label>
                <input
                  type="date"
                  value={meetingDate}
                  onChange={(e) => setMeetingDate(e.target.value)}
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">회의일시를 입력하지 않을 시 오늘 날짜로 진행됩니다.</p>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><Users className="w-3.5 h-3.5" /> 참석자 (선택)</label>
                <TagAutocomplete
                  value={attendees}
                  onChange={setAttendees}
                  suggestions={memberNames}
                  placeholder="이름 선택 또는 직접 입력"
                />
              </div>
            </div>

            <div className="flex flex-col">
              <div className="flex justify-between items-center mb-1">
                <label className="block text-sm font-medium">원본 내용 (회의록/메모)</label>
                <button
                  type="button"
                  onClick={handleLoadSample}
                  className="text-xs font-semibold text-blue-500 hover:text-blue-600 bg-blue-500/10 px-3 py-1 rounded-full transition-colors"
                >
                  랜덤 샘플 불러오기
                </button>
              </div>
              <textarea
                required
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="회의 내용이나 기획 아이디어를 자유롭게 작성하세요."
                className="w-full min-h-[220px] bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm leading-relaxed"
              />
            </div>
          </form>
        </div>

        <div className="flex justify-end gap-3 p-5 border-t border-border shrink-0 bg-black/5 dark:bg-white/5">
          <button
            type="button"
            onClick={() => onClose()}
            className="px-5 py-2.5 font-medium text-sm text-muted-foreground hover:bg-black/10 dark:hover:bg-white/10 rounded-lg transition-colors"
          >
            취소
          </button>
          <button
            form="doc-form"
            type="submit"
            disabled={isLoading || !content.trim() || (isCreatingNewProject && !newProjectName.trim())}
            className="flex items-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 px-8 py-2.5 rounded-lg transition-colors text-sm font-medium shadow-lg shadow-primary/20 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            문서 저장 및 시작하기
          </button>
        </div>
      </div>
    </div>
  );
}
