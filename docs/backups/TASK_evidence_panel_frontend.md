# 원문 연동 UI — 프론트엔드 패널 구현 요청서

이 문서는 Claude가 작성해 Codex에게 넘기는 작업 지시서입니다. 백엔드 준비는 끝났고, 이번 작업은 **프론트엔드만** 건드립니다.

---

## 1. 목표

기획서 화면(`documents/page.tsx`)에서 특정 항목(우선 5번 주요 기능부터) 옆에 `[원문 보기]` 버튼을 달아, 클릭하면 오른쪽에 **회의록 전체 원문**이 슬라이드로 열리고 해당 항목의 근거 문장이 하이라이트되도록 만듭니다.

### 요구되는 동작

1. 기본 화면에는 원문 패널이 안 보인다 (버튼 누를 때만 열림).
2. `[원문 보기]` 클릭 → 오른쪽에 패널이 열리고, **회의록 전체**가 표시된다 (근거 문장만 잘라서 보여주면 안 됨).
3. 해당 항목의 근거 문장이 시각적으로 강조되고(예: 노란 배경), 화면 스크롤이 그 위치로 자동 이동한다.
4. 사용자는 패널 안에서 위아래로 자유롭게 스크롤해 앞뒤 맥락을 볼 수 있다.
5. 패널은 닫기 버튼 또는 배경(오버레이) 클릭으로 닫힌다.
6. 하나의 항목에 근거가 여러 개면(quotes 배열 길이 > 1), 가능하면 각각을 구분해 보여준다(꼭 복잡하게 만들 필요는 없음 — 전부 하이라이트만 해도 충분).

---

## 2. 이미 준비된 것 (백엔드) — 여기는 건드리지 마세요

### 2-1. `SpecDocument.evidence_items` (신규 필드, 이미 DB·API에 반영됨)

- 모델: `backend/meetings/models.py`의 `SpecDocument.evidence_items` (TextField, JSON 문자열)
- 채우는 로직: `backend/meetings/services.py`의 `_build_evidence_items()` (이미 구현·테스트 완료, `run_meeting_analysis` 안에서 호출됨)
- API 노출: `backend/meetings/serializers.py`의 `SpecDocumentSerializer`에 `evidence_items` 필드 포함됨 → 프론트가 스펙(spec) 객체를 받을 때 `spec.evidence_items`로 이미 옵니다 (JSON 문자열이라 `JSON.parse` 필요).

**JSON 파싱 후 형태**:

```json
{
  "key_features": {
    "quotes": ["섹션 전체 근거 인용문1", "인용문2"],
    "items": [
      { "title": "예약 알림 이중 발송", "quotes": ["원문 인용문 A", "원문 인용문 B"] },
      { "title": "복약 알림 스케줄링", "quotes": ["원문 인용문 C"] }
    ]
  },
  "overview": { "quotes": ["..."] },
  "problem_definition": { "quotes": ["..."] },
  "target_users": { "quotes": ["..."] },
  "tech_stack": { "quotes": ["..."] },
  "final_decisions": { "quotes": ["..."] }
}
```

- 키는 **`SpecDocument`의 실제 필드명**(스네이크케이스: `overview`, `problem_definition`, `target_users`, `key_features`, `tech_stack`, `final_decisions`)입니다. `goals`는 이번엔 안 채워집니다(node②가 goals를 아직 항목 단위 evidence로 안 넘겨서 — 있으면 쓰고 없으면 그냥 빈 채로 두면 됩니다).
- **`items`(항목 단위 세분화)는 지금 `key_features`에만 있습니다.** 다른 섹션은 `quotes`(섹션 전체 근거 목록)만 있고 항목별로 안 쪼개져 있습니다. 이번 작업은 **5번(주요 기능)부터** 시작하는 이유가 이것입니다 — 데이터가 이미 준비된 유일한 섹션이라서요.
- 근거가 없는 섹션은 키 자체가 없을 수 있습니다(빈 문자열이 아니라 키 누락) — 없으면 그냥 `[원문 보기]` 버튼을 숨기거나 비활성화하면 됩니다.

### 2-2. 회의록 원문 전체

- `NoteDto.content` (이미 프론트 타입에 있고, 노트를 불러올 때 이미 같이 옵니다 — 새 API 호출 필요 없음). `documents/page.tsx`의 `type NoteDto` 참고.

### 2-3. 참고할 기존 코드 패턴 — 반드시 확인하고 시작하세요

`evidence_data`(기존, 섹션 전체를 문자열 하나로 뭉친 옛날 필드)를 프론트가 어떻게 다루는지 이미 코드가 있습니다. `evidence_items`도 **같은 패턴**을 따라 만드세요:

- `frontend/src/components/documents/ProposalTemplate.tsx`
  - `export type ProposalEvidence = Partial<Record<"projectOverview" | "problemDefinition" | ... , string>>` — 백엔드 필드명과 다른 **카멜케이스 별칭**을 씁니다.
- `frontend/src/app/(dashboard)/documents/page.tsx` (2950번째 줄 근처)
  - `EVIDENCE_KEY_ALIASES`: 백엔드 스네이크케이스 필드명 → 프론트 카멜케이스 키 매핑 테이블
  - `parseProposalEvidence(raw: string | null): ProposalEvidence`: `evidence_data` JSON 문자열을 파싱해서 위 별칭으로 매핑하는 함수

**`evidence_items`도 이 구조를 그대로 재사용하거나 나란히 만드세요** — 완전히 새로운 명명 규칙을 만들지 말고, 이미 있는 `EVIDENCE_KEY_ALIASES` 매핑을 참고해서 일관되게 갑니다.

### 2-4. 확인 필요: 프론트 타입에 `evidence_items`가 아직 없습니다

`page.tsx`의 `type SpecDto`(54번째 줄 근처)에는 `evidence_data: string | null;`만 있고 `evidence_items`는 아직 없습니다. 백엔드 API 응답에는 이미 포함되지만, 프론트 타입 선언에 **`evidence_items: string | null;`을 먼저 추가**해야 컴파일 에러 없이 쓸 수 있습니다. 이게 사실상 첫 번째로 할 일입니다.

---

## 3. 건드리면 안 되는 기존 UI

`documents/page.tsx` 안에 **"원본 회의록 / 메모"**라는 접이식 텍스트박스가 이미 있습니다(`rawNoteOpen`, `rawDraft` 상태, 기획서 바로 위에 위치). 이건 **기획서 생성 전에 회의록을 직접 편집하는 용도**이고, 생성 후에는 잠깁니다(`rawLocked`).

**이번에 만드는 원문 보기 패널은 이것과 별개의 새 컴포넌트입니다.** 기존 걸 고치거나 재사용하려 하지 말고, 완전히 새로 만드세요. 용도가 다릅니다(하나는 편집용, 하나는 근거 확인용 읽기 전용 뷰어).

---

## 4. 구현 범위 (Phase 1 — 지금 바로 만들 수 있는 것)

1. **파싱 유틸**: `parseEvidenceItems(raw: string | null)` 같은 함수를 `parseProposalEvidence` 옆에 추가. `EVIDENCE_KEY_ALIASES`와 동일한 키 매핑을 재사용하세요.
2. **`EvidencePanel` 컴포넌트** (신규 파일 권장, 예: `frontend/src/components/documents/EvidencePanel.tsx`)
   - props: `open: boolean`, `onClose: () => void`, `fullText: string`(= `note.content`), `targetQuotes: string[]`
   - 오른쪽 고정 위치(`position: fixed; right: 0`), 슬라이드 인/아웃 트랜지션
   - 배경 오버레이 (클릭 시 닫힘)
   - `fullText`를 그대로 렌더링하되, `targetQuotes` 중 원문에서 찾은 것만 하이라이트(`<mark>` 또는 배경색 있는 `<span>`)
   - 하이라이트된 부분으로 자동 스크롤 (React `ref` + `scrollIntoView({ block: "center" })` 권장)
3. **5번 주요 기능에 `[원문 보기]` 버튼 연결 — 여기 함정이 하나 있습니다**

   `ProposalTemplate.tsx:247-257`를 보면 5번은 지금 **개별 기능 카드가 아니라 HTML 문자열 하나**(`doc.features`)를 `<RichText html={doc.features} />` (또는 `<EditableRichText>`)로 통째로 렌더링합니다. `<p><strong>기능명</strong></p><p>설명</p>`이 기능 개수만큼 이어붙은 하나의 blob이라, 그 안에 기능별로 React 버튼을 끼워 넣는 건 (dangerouslySetInnerHTML 특성상) 간단하지 않습니다.

   **Phase 1에서는 아래 방식을 권장합니다** (렌더링 구조를 갈아엎지 않는 쪽):
   - 기존 `doc.features` HTML 블록은 그대로 두고, 그 아래(또는 옆)에 `evidence_items.key_features.items[]`를 순회하는 **별도의 작은 버튼 목록**을 추가하세요. 예: "근거 보기: [기능명1] [기능명2] [기능명3]" 형태로 기능명마다 버튼 하나씩.
   - 각 버튼 클릭 시 `items[i].quotes`를 `targetQuotes`로 넘겨 패널을 엽니다.
   - `items[i].title`이 HTML 안의 실제 기능명과 순서·내용이 같이 만들어지므로(생성 시 같은 `Feature` 배열에서 나옴), 버튼 라벨에 그 title을 그대로 쓰면 사용자가 어떤 기능인지 바로 알 수 있습니다.

   **더 자연스러운 형태(카드 하나하나에 인라인으로 버튼)를 원하면**, 5번 렌더링 자체를 "HTML 문자열 하나"에서 "기능 배열을 map으로 그리기"로 바꿔야 합니다 — 이건 범위가 더 커서(백엔드가 `key_features` HTML 대신 구조화된 기능 배열을 따로 내려줘야 할 수도 있음) 이번 Phase 1의 필수 범위는 아닙니다. 시간 되면 시도해도 되지만, 안 되면 위의 "별도 버튼 목록" 방식으로 충분합니다.

---

## 5. Phase 2 — 아직 준비 안 됨, 이번엔 만들지 마세요 (또는 껍데기만)

PM 확인사항 쪽의 `[원문 보기]` + `[적용]`/`[적용하지 않음]`은 **원래 요구사항에는 있었지만, 아직 백엔드가 준비가 안 됐습니다**:

- PM 확인사항은 지금 그냥 문자열 하나(`content_html` 안의 `<li>` 텍스트)로만 저장돼 있고, "적용하면 정확히 이 문장이 본문에 들어간다"는 걸 구분할 수 있는 별도 데이터(`candidate_text`)가 아직 없습니다.
- `[적용]`을 눌렀을 때 실제로 문서를 바꿔주는 API 엔드포인트도 아직 없습니다.

**이번 Phase 1에서는 PM 확인사항용 버튼을 만들지 마세요.** 만약 UI 틀만 미리 잡아두고 싶다면 `[적용]`/`[적용하지 않음]`은 `disabled`로 두고 "준비 중" 툴팁 정도만 붙이는 걸 권장합니다. 이 부분은 백엔드 작업(PM 확인사항 구조화 + 적용 API)이 끝난 뒤 별도 작업으로 이어집니다.

---

## 6. 구현할 때 주의할 것

- **근거 문장이 원문에 항상 정확히(글자 하나까지) 일치하지는 않을 수 있습니다.** 검증 로직이 유사도 매칭을 쓰는 경우가 있어서요. `fullText.indexOf(quote)`로 못 찾으면 **조용히 하이라이트 없이 원문만 보여주세요** — 에러를 던지거나 화면이 깨지면 안 됩니다.
- `evidence_items`에 아예 데이터가 없는 섹션(예: `goals`)은 `[원문 보기]` 버튼을 안 보여주거나 비활성화하세요.
- 근거 문장에 HTML 특수문자가 있을 수 있으니 하이라이트 처리 시 XSS 주의(기존 코드처럼 React의 기본 이스케이프를 활용하고 `dangerouslySetInnerHTML`은 꼭 필요한 곳에만, DOMPurify 거쳐서 쓰세요 — `ProposalTemplate.tsx`의 `sanitizeRestrictedHtml` 참고).

---

## 7. 완료 기준

- [ ] 5번 각 기능마다 `[원문 보기]` 버튼이 보인다 (카드 인라인이든 별도 목록이든 상관없음, 근거가 있는 기능만)
- [ ] 클릭하면 오른쪽에 회의록 **전체** 원문이 열린다 (일부만 잘라서 X)
- [ ] 해당 기능의 근거 문장이 하이라이트되고 그 위치로 자동 스크롤된다
- [ ] 패널을 닫을 수 있다 (X 버튼, 배경 클릭)
- [ ] 다른 기능의 `[원문 보기]`를 누르면 그 근거로 다시 이동한다
- [ ] 기존 "원본 회의록 / 메모" 편집 박스는 그대로 정상 작동한다 (안 건드렸는지 확인)
- [ ] 근거를 원문에서 못 찾는 경우에도 에러 없이 정상 동작한다

---

## 8. 참고 파일 경로

| 파일 | 용도 |
|---|---|
| `backend/meetings/services.py` | `_build_evidence_items()` — 데이터가 어떻게 만들어지는지 |
| `backend/meetings/serializers.py` | `evidence_items` API 노출 지점 |
| `backend/meetings/models.py` | `SpecDocument.evidence_items` 필드 정의 |
| `frontend/src/app/(dashboard)/documents/page.tsx` | `NoteDto`, `SpecDto` 타입, `EVIDENCE_KEY_ALIASES`, `parseProposalEvidence`, "원본 회의록" 박스(건드리지 말 것), 5번 렌더링 호출부 |
| `frontend/src/components/documents/ProposalTemplate.tsx` | `ProposalEvidence` 타입, 섹션 렌더링, `sanitizeRestrictedHtml` |
