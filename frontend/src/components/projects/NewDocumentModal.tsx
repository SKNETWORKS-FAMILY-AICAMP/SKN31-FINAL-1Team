"use client";

import { useState, useRef, useEffect } from "react";
import { X, Loader2, Paperclip, FileText, Users, CalendarIcon, FolderKanban } from "lucide-react";
import { useRouter } from "next/navigation";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

type ProjectOption = { id: string; name: string };
const NEW_PROJECT_VALUE = "__new__";

// 샘플마다 "프로젝트 기간: 시작 ~ 종료"를 명시해둔다 — 이 기간이 기획서 생성 시 함께 추출되어,
// 나중에 업무분배(WBS) 탭에서 오늘 날짜 대신 이 시작일부터 자동으로 일정이 잡히는 데 쓰인다.
// 2026-08-27: 다운스트림(AI 기획서/요구사항정의서 생성)이 "회의록에 있는 정보만" 근거로
// 작성되기 때문에, 샘플 자체가 빈약하면 아무리 프롬프트를 다듬어도 결과물이 풍부해질 수 없다.
// 배경/문제의식/제약사항/예외 상황/비기능 요구사항까지 담아 실제 기획 회의록 수준으로 채웠다.
const SAMPLE_NOTES = [
  `[신규 쇼핑몰 프로젝트 킥오프 회의록]
일자: 2026-08-19
프로젝트 기간: 2026-08-25 ~ 2026-10-24 (약 2개월)
참석자: PM, 개발팀장, 디자인팀장, 마케팅팀장

1. 배경 및 문제의식
- 기존 자사몰 앱은 출시 3년 차로 최근 6개월간 재방문율이 전년 대비 18% 하락했고, 특히 야간 시간대(21시~02시) 이탈률이 높다는 데이터가 있음 — 야간 사용성(다크모드 부재)이 원인 중 하나로 추정됨.
- 신규 회원가입 단계에서 이탈이 큰데, 설문 결과 "이메일 회원가입 절차가 번거롭다"는 응답이 가장 많았음 → 소셜 로그인 부재가 원인으로 지목됨.
- 마케팅팀 요청: 체류시간 대비 구매전환이 낮은 사용자에게 개인화 추천을 노출해 전환율을 끌어올리고 싶음.

2. 결정 사항 (이번 리뉴얼에서 반드시 포함)
- 다크모드: 시스템 설정 연동 + 앱 내 수동 전환 스위치 둘 다 지원. 1차로 메인, 상품 상세, 장바구니 화면부터 적용하고 나머지 화면은 2차 스프린트에서 순차 적용.
- 소셜 로그인: 카카오·구글·네이버 3개사 우선 지원. 최초 소셜 로그인 시 기존 이메일 계정과 이메일이 같으면 자동 연동 여부를 사용자에게 물어보고, 다르면 신규 계정으로 생성.
- AI 상품 추천: 최근 30일 검색 기록 + 장바구니 데이터를 기반으로 메인 화면 하단에 "회원님을 위한 추천" 섹션 노출. 비로그인 사용자에게는 인기 상품 기준으로 대체 노출.
- 결제 모듈은 기존 PG사(토스페이먼츠) 연동을 그대로 유지하고, 이번 스코프에서는 UI(디자인)만 다크모드에 맞춰 개선한다 — PG 연동 로직 자체는 건드리지 않음.

3. 비기능/제약 사항
- 다크모드 전환 시 깜빡임(FOUC) 없이 즉시 반영되어야 함(디자인팀장 강조).
- 소셜 로그인 연동은 각 사(카카오/구글/네이버) 앱 심사가 필요하므로, 개발 완료 후 최소 1주는 심사 기간으로 일정에 반영할 것(개발팀장 지적).
- AI 추천 API는 기존 검색 인프라에 부하를 주지 않도록 별도 배치(batch)로 하루 1회 추천 후보군을 미리 계산해두는 방식으로 설계.

4. 다음 액션
- 디자인팀: 8/26까지 다크모드 시안 1차 초안 공유.
- 개발팀: 8/28 소셜 로그인 3사 API 키 발급 신청.`,

  `[내부 인트라넷 인사관리 기능 추가 회의록]
일자: 2026-08-20
프로젝트 기간: 2026-08-26 ~ 2026-09-25 (약 1개월)
참석자: 인사팀장, IT지원팀, 총무팀 담당자

1. 배경 및 목적
- 현재 '연차 휴가 신청'과 '출장 보고서'를 엑셀과 이메일로 관리하고 있는데, 인사팀 기준 월평균 40건 이상의 신청을 수기로 취합하다 보니 누락·중복 승인 사고가 최근 2건 발생함. 이를 인트라넷 시스템 내로 전산화해 처리 이력을 남기고 결재 누락을 방지하는 것이 목적.
- 총무팀 요청사항: 출장 경비 정산과 연계될 수 있도록 영수증 첨부 기능이 특히 중요함(이번 스코프는 첨부까지만, 정산 자동화는 차기 과제).

2. 연차 신청 기능 상세
- 달력 UI에서 시작일/종료일 선택. 주말·공휴일은 자동으로 신청 대상에서 제외(카운트 안 함).
- 반차(오전/오후) 선택 옵션 제공 — 반차는 0.5일로 잔여 연차에서 차감.
- 신청 즉시 담당 팀장에게 사내 메신저 + 이메일 동시 알림 발송, 상태는 '결재 대기'로 전환.
- 팀장이 반려할 경우 반려 사유를 필수로 입력해야 하며, 신청자에게 즉시 알림.
- 잔여 연차가 부족하면 신청 시점에 경고 문구를 보여주되, 신청 자체는 막지 않는다(무급 처리는 인사팀이 별도 확인).

3. 출장 보고서 기능 상세
- 출장 종료일 기준 3일 이내 미작성 시 매일 알림 발송(3일째부터는 팀장에게도 참조 알림).
- 영수증은 이미지 파일(JPG/PNG/PDF) 다중 첨부 가능, 개당 최대 10MB.
- 모바일에서 카메라로 촬영해 바로 업로드 가능해야 함 — 사용 시나리오 대부분이 출장지에서 모바일로 작성되기 때문에 모바일 반응형 최적화가 필수(IT지원팀 강조).
- 출장 보고서도 연차와 동일하게 팀장 결재 프로세스를 거친다.

4. 제약 사항
- 기존 사번 체계(사번 5자리) 및 조직도 데이터는 그대로 연동해서 쓴다 — 별도 사용자 마스터를 새로 만들지 않음.
- 개인정보(주민등록번호 등)는 이 기능 범위에 포함되지 않으며, 인사 정보 조회 권한은 인사팀만 갖는다.

5. 결정 사항
- 연차 신청은 반차(오전/오후) 옵션까지 포함해 이번 스코프에 반드시 넣기로 확정함.
- 출장 보고서 영수증 첨부는 이미지 파일 다중 첨부까지만 지원하고, 경비 정산 자동화는 이번 범위에서 제외하고 차기 과제로 넘기기로 함.
- 사용자 마스터는 새로 만들지 않고 기존 사번 체계·조직도를 그대로 연동하기로 결정함.`,

  `[HeyZzabi V3 대규모 업데이트 기획 회의]
일자: 2026-08-22
프로젝트 기간: 2026-08-24 ~ 2026-11-22 (약 3개월)
참석자: 전사 직원 (PM 주관)

1. 배경
- 현재 칸반 카드가 "할 일 1개 = 카드 1개" 단위로만 관리되다 보니, 실제로는 여러 세부 작업으로 구성된 일도 카드 하나에 뭉뚱그려져 진행 상황 파악이 어렵다는 피드백이 반복적으로 접수됨.
- 파일 공유는 현재 사내 메신저로만 이루어져 어떤 파일이 어떤 카드와 관련 있는지 추적이 안 되고, Slack/Github 알림도 수동으로 전달하고 있어 놓치는 경우가 잦음.

2. 결정 사항
- 하위 체크리스트(Sub-tasks): 칸반 카드 내부에 체크리스트 항목을 추가할 수 있고, 각 항목마다 별도 담당자를 지정할 수 있어야 함. 카드 전체 진행률은 체크된 항목 비율로 자동 계산해 카드 앞면에 표시.
- 파일 첨부 고도화: 드래그 앤 드롭으로 칸반 카드에 여러 파일을 한 번에 올릴 수 있게 지원. 첨부된 파일은 카드 뒷면(상세 모달)에서 목록으로 확인 가능해야 함.
- 슬랙 연동: 특정 카드 상태가 'Done(완료)'으로 바뀌면, 사전에 프로젝트별로 등록된 슬랙 웹훅으로 "완료되었습니다" 메시지가 자동 발송되어야 함. 실패 시(웹훅 오류 등) 카드에 실패 표시를 남겨 재시도할 수 있게 한다.
- 깃허브 연동: 카드에 깃허브 PR 주소를 입력하면, PR의 현재 상태(Open/Merged/Closed)를 뱃지 형태로 카드에 표시. 상태는 실시간이 아니어도 되고, 카드 조회 시점에 갱신되면 충분함(전사 합의).

3. 우선순위 논의
- 하위 체크리스트는 전사 대다수가 가장 시급하다고 답해 최우선으로 진행하기로 결정.
- 슬랙/깃허브 연동은 있으면 좋지만 이번 분기 내 필수는 아니라는 의견도 있어, 체크리스트·파일첨부 이후 순서로 진행.

4. 비고
- 기존에 중복 구현되어 있던 칸반 보드 컴포넌트를 이번 기회에 하나로 통합하자는 제안이 나왔으나, 이번 회의에서는 화면 기능 범위만 논의하고 통합 여부는 개발팀 내부 판단에 맡기기로 함.`,
];

export function NewDocumentModal({
  defaultProjectId,
  onClose,
}: {
  // 문서생성 페이지가 현재 보고 있는 프로젝트가 있으면 기본 선택값으로 넘겨준다 — 없어도(첫 사용) 동작함
  defaultProjectId?: string;
  onClose: (projectId?: string, createdDocId?: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState("");
  const [attendees, setAttendees] = useState<string[]>([]);
  const [memberNames, setMemberNames] = useState<string[]>([]);
  const [content, setContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isParsingFile, setIsParsingFile] = useState(false);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // 프로젝트 선택 — 기존 프로젝트 중 고르거나, 그 자리에서 새 프로젝트 이름만 입력해 바로 만들 수 있다.
  // (아직 단일 프로젝트 전제가 남아있는 화면들이 있어, 여기서 만든 프로젝트가 다른 화면에 바로 안 보일 수 있음은 알려진 제약)
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(defaultProjectId ?? "");
  const [newProjectName, setNewProjectName] = useState("");

  useEffect(() => {
    const loadProjects = async () => {
      try {
        const res = await fetch("/api/projects");
        const list = await res.json();
        const arr: ProjectOption[] = Array.isArray(list) ? list : list.data || [];
        setProjects(arr);
        if (!defaultProjectId) {
          setSelectedProjectId(arr.length > 0 ? arr[0].id : NEW_PROJECT_VALUE);
        }
      } catch {
        setSelectedProjectId(NEW_PROJECT_VALUE);
      } finally {
        setLoadingProjects(false);
      }
    };
    loadProjects();
  }, [defaultProjectId]);

  // 참석자 드롭박스 후보 — DB에 등록된 사람 이름. 목록에 없는 사람은 TagAutocomplete에서 직접 입력해 추가할 수 있다.
  // 온보딩 전이라 이름이 비어있는 계정을 걸러내지 않으면 라벨 없는 빈 체크박스가 뜬다(다른 화면들과 동일한 필터).
  useEffect(() => {
    fetch("/api/users")
      .then(res => res.json())
      .then(json => setMemberNames((json.data ?? []).filter((u: any) => u.name?.trim()).map((u: any) => u.name)))
      .catch(() => {});
  }, []);

  // 내용에서 제목을 뽑아낸다 — 회의록이 보통 "[제목처럼 생긴 첫 줄]"로 시작하므로 대괄호 안쪽을 우선 사용
  const deriveTitleFromContent = (text: string) => {
    const firstLine = text.split("\n").map(l => l.trim()).find(l => l.length > 0) ?? "";
    const bracketMatch = firstLine.match(/^\[(.+)\]$/);
    const base = (bracketMatch ? bracketMatch[1] : firstLine).slice(0, 40);
    return base || `새 문서 ${new Date().toLocaleTimeString()}`;
  };

  // 본문에서 회의 일시를 뽑아낸다 — "일자/날짜/회의일시/작성일" 같은 키워드가 있는 줄을 우선
  // 찾고, 없으면 본문 전체에서 처음 나오는 날짜 형식을 그대로 쓴다. YYYY-MM-DD, YYYY.MM.DD,
  // "YYYY년 M월 D일" 형태를 지원한다(SAMPLE_NOTES와 실제 회의록에서 흔한 표기 둘 다 커버).
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

  // 회의록 본문이 바뀔 때마다(파일 첨부든 직접 입력이든) 회의 일시/참석자를 자동으로 채운다.
  // 이미 사용자가 채운 값은 절대 덮어쓰지 않는다 — meetingDate/attendees를 의도적으로 의존성
  // 배열에서 빼서, 이 값들이 바뀌는 것 자체(예: 사용자가 직접 고르거나 지움) 때문에 이 효과가
  // 다시 도는 걸 막는다(안 그러면 사용자가 지운 참석자가 다시 자동으로 붙는 등 사용자 입력과
  // 충돌한다). 타이핑 중 우연히 날짜처럼 보이는 숫자에 매번 반응하지 않도록 살짝 debounce.
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
    // 이미 직접 입력해둔 제목이 있으면 덮어쓰지 않는다 — 샘플은 "내용"만 채워주는 용도
    if (!title.trim()) setTitle(deriveTitleFromContent(sample));
  };

  const handleFilePicked = async (file: File) => {
    setError("");
    setIsParsingFile(true);
    setFileName(file.name);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/documents/parse-file", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok) {
        setContent(data.text);
        if (!title.trim()) setTitle(file.name.replace(/\.[^/.]+$/, ""));
      } else {
        setError(data.error || "파일 처리에 실패했습니다.");
        setFileName("");
      }
    } catch {
      setError("파일 업로드 중 오류가 발생했습니다.");
      setFileName("");
    } finally {
      setIsParsingFile(false);
    }
  };

  const isCreatingNewProject = selectedProjectId === NEW_PROJECT_VALUE;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    if (isCreatingNewProject && !newProjectName.trim()) return;

    // 제목을 안 적었으면 내용에서 자동으로 뽑아 채운다
    const finalTitle = title.trim() || deriveTitleFromContent(content);
    // 회의 일시를 안 골랐으면 오늘 날짜로 진행한다 — toISOString()은 UTC 변환으로 하루가 밀릴 수 있어
    // 로컬 연/월/일을 직접 조합한다(이 프로젝트에서 이미 여러 번 겪은 타임존 버그 패턴).
    const todayLocal = (() => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    })();
    const finalMeetingDate = meetingDate || todayLocal;

    setIsLoading(true);
    try {
      let targetProjectId = selectedProjectId;

      // "+ 새 프로젝트" 선택 시 문서 저장 전에 프로젝트부터 생성한다.
      // POST /api/projects는 tasks 배열을 map()하므로 빈 배열을 명시적으로 넘겨야 한다.
      if (isCreatingNewProject) {
        const projectRes = await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newProjectName.trim(), tasks: [] }),
        });
        if (!projectRes.ok) throw new Error("프로젝트 생성 실패");
        const newProject = await projectRes.json();
        targetProjectId = newProject.id;
      }

      const res = await fetch(`/api/projects/${targetProjectId}/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: finalTitle,
          rawContent: content,
          meetingDate: finalMeetingDate,
          attendees: attendees.length > 0 ? attendees.join(", ") : undefined,
        }),
      });

      if (!res.ok) {
        throw new Error("생성 실패");
      }
      const createdDoc = await res.json();

      router.refresh();
      onClose(targetProjectId, createdDoc?.id);
    } catch (error) {
      console.error(error);
      alert("문서 생성 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-5xl border border-border flex flex-col max-h-[95vh]">
        <div className="flex justify-between items-center p-5 border-b border-border shrink-0">
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="w-6 h-6 text-primary" />
              새 회의록 / 문서 작성
            </h2>
            <p className="text-muted-foreground text-sm mt-1">회의 내용을 직접 입력하거나 문서 파일을 첨부하세요.</p>
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
            {/* 문서 제목(넓게) + 프로젝트 선택(좁게)을 한 줄에 — 문서를 어느 프로젝트에 등록할지
                여기서 바로 고르거나, 프로젝트가 하나도 없으면 "+ 새 프로젝트"로 그 자리에서 만든다 */}
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

            {/* 좌: 파일 첨부 / 우: 직접 입력 — 파일을 첨부하면 파싱된 텍스트가 우측 원본 내용 textarea로 그대로 채워진다(handleFilePicked) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              <div className="flex flex-col">
                <label className="block text-sm font-medium mb-1">파일 첨부</label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.md,.docx,.pdf,.hwp"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFilePicked(f); }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isParsingFile}
                  className="flex-1 min-h-[130px] w-full flex flex-col items-center justify-center gap-2 py-3 px-4 rounded-xl border-2 border-dashed border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground transition-all disabled:opacity-60 text-center"
                >
                  <div className="p-2.5 rounded-full bg-black/5 dark:bg-white/5">
                    {isParsingFile ? <Loader2 className="w-5 h-5 animate-spin" /> : <Paperclip className="w-5 h-5" />}
                  </div>
                  <span className="font-medium text-sm">
                    {isParsingFile ? "파일에서 텍스트를 추출하는 중..." : fileName ? `${fileName} 첨부됨 (다시 선택하려면 클릭)` : "문서 파일 첨부"}
                  </span>
                  <span className="text-xs opacity-70">.txt / .md / .docx / .pdf / .hwp</span>
                </button>
              </div>

              <div className="flex flex-col">
                <div className="flex justify-between items-center mb-1">
                  <label className="block text-sm font-medium">원본 내용 (회의록/메모) — 직접 입력</label>
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
                  placeholder="회의 내용이나 기획 아이디어를 자유롭게 작성하거나, 왼쪽에서 파일을 첨부하면 여기에 자동으로 채워집니다."
                  className="flex-1 min-h-[130px] w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm leading-relaxed"
                />
              </div>
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
