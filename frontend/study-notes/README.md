# study-notes — 프론트엔드 학습용 사본

이 폴더의 파일들은 **실제 앱에서 쓰이지 않습니다.** 어디서도 import되지 않고, `npm run build`에도 영향을 주지 않습니다.

React / Next.js / TypeScript를 처음 배우는 사람이 실제 코드 패턴을 촘촘한 한글 주석과 함께 읽을 수 있도록, 저장소의 핵심 파일 몇 개를 발췌해 학습용으로 다시 옮겨 적은 것입니다. 원본 파일이 바뀌어도 이 폴더는 자동으로 갱신되지 않으니, 실제 동작 기준은 항상 원본 파일입니다.

| 파일 | 원본 |
| --- | --- |
| `01_layout_구조.study.tsx` | `src/app/layout.tsx`, `src/app/(dashboard)/layout.tsx` |
| `02_로그인_흐름.study.tsx` | `src/lib/auth.tsx` |
| `03_apiFetch.study.ts` | `src/lib/api/client.ts` |
| `04_문서생성_데이터.study.tsx` | `src/app/(dashboard)/documents/page.tsx` (일부 발췌) |
| `05_음성업로드.study.tsx` | `src/components/projects/NewDocumentModal.tsx` (일부 발췌) |

읽는 순서는 숫자 순서대로 추천합니다. 각 파일 끝에 "🧪 스스로 확인해볼 것" 문제가 있으니 답을 소리 내어 말해보고, 막히면 원본 파일을 열어 같은 함수 이름을 검색해서 앞뒤 맥락을 확인하세요.
