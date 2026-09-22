# 기획서 생성 안정화 작업 인수인계

작성일: 2026-09-21  
저장소: `/home/playdata/projects/SKN31-FINAL-1Team`

## 1. 최종 목표

회의록 원문으로 7개 섹션의 기획서를 생성한다. 장문·단문·정리된 회의록 모두에서
중요 내용을 누락하지 않으면서 서비스 가능한 시간 안에 끝나야 한다.

이번 작업은 구조를 다시 탐색하는 실험이 아니다. 아래에 고정한 최종 구조를 구현하고
정해진 기준으로 검증하는 작업이다.

## 2. 현재 사용자에게 발생한 문제

최근 웹에서 기획서를 생성했을 때 두 문제가 차례로 발생했다.

1. 모든 섹션이 `회의에서 논의되지 않았습니다.`로 저장됨
2. 이를 고치기 위해 웹에 회의록 구조화 노드를 다시 연결하자 생성이 7분 이상 걸림

직접 원인은 다음과 같다.

- `ai/plan_draft/agent.py`의 운영 기본값을 `hybrid`로 변경했다.
- `hybrid`는 앞 단계의 `project/users/requirements/decisions` 구조화 데이터가 있어야 한다.
- 당시 `backend/meetings/services.py`는 구조화 노드를 실행하지 않고 빈 딕셔너리를
  기획서 노드에 전달하고 있었다.
- 빈 문서를 막기 위해 `meeting_analysis.node.run()`을 웹 경로에 다시 연결했다.
- 장문 구조화 노드는 전체 개요, 여러 청크, 결정 후보 정리를 여러 LLM 호출로 수행해
  웹 생성 시간이 다시 수분 단위로 증가했다.

현재 웹에 연결된 `구조화 노드 → hybrid 기획서` 상태는 최종안이 아니다.

## 3. 이미 측정된 결과

### indexed 전략

`meeting_musinsa_long.txt` 실측:

- 전체 826.184초
- 사실 인덱스: 435.165초, 2회 시도, 54,715토큰
- 전체 기획서: 390.687초, 2회 시도, 74,268토큰
- 필수 회수율 0.50
- 누락: `storage_split`, `resale_priority`
- 서비스 불가

결론: 별도 사실 인덱스 LLM은 비용·시간 대비 품질 효과가 없으므로 운영 경로에서 사용하지 않는다.

### hybrid 전략

기존 구조화 JSON을 넣은 `meeting_musinsa_long.txt` 실측:

- 전체 128.466초
- LLM 호출 1회, 128.314초
- 재시도 없음
- 38,772 input / 2,916 output / 41,688 total tokens
- 필수 회수율 0.25
- 누락: `main_purpose`, `dictionary_tables`, `resale_priority`

결론: 속도는 통과했지만 구조화 결과와 기획서 LLM 사이에서 중요 내용이 누락됐다.
현재 형태 그대로 운영하면 안 된다.

### 전체 테스트

마지막 AI 전체 테스트 결과:

- 444 passed
- 2 skipped

백엔드 `meetings/tests.py`는 `MYSQL_HOST=`로 SQLite를 강제하면 7개가 통과한다.
기본 `.env`는 외부 RDS를 가리켜 샌드박스에서 DNS 오류가 난다.

## 4. 최종 구조 — 변경 금지

웹 기획서 생성 시 무거운 `meeting_analysis` 전체 구조화 노드를 실행하지 않는다.

회의록 원문을 두 개의 독립된 LLM 작업으로 나눠 **병렬 실행**한다.

### 호출 A: 콘텐츠 기획

한 번의 호출에서 다음을 함께 생성한다.

- 1. 프로젝트 개요
- 2. 핵심 목표
- 3. 세부 목표 및 문제 정의
- 4. 대상 사용자
- 5. 주요 기능

### 호출 B: 기술·결정

한 번의 호출에서 다음을 함께 생성한다.

- 6. 기술 스택 및 제약사항
- 7. 최종 결정사항

### 병합

- A와 B는 `ThreadPoolExecutor(max_workers=2)`로 동시에 실행한다.
- 두 호출 모두 전체 회의록 원문을 직접 읽는다.
- 렌더링 단계에서 evidence.quote가 원문에 정확히 존재하는지 코드로 검증한다.
- 두 호출 결과를 `PlanDocument` 7개 섹션으로 결정적으로 합친다.
- 결정과 PM 확인 사항의 충돌은 코드로 정리한다.
- 전체 검수 LLM, 사실 인덱스 LLM, 세 번째 LLM 호출을 추가하지 않는다.

이 구조를 선택한 이유:

- 전체 기획서 단일 호출은 기술·최종 결정이 다른 섹션에 밀려 누락됐다.
- 사실 인덱스 선행 호출은 7분 이상 걸리면서도 필수 결정을 놓쳤다.
- 기존 다중 호출 구조화 노드는 웹에서 전체 시간이 7분 이상 걸린다.
- 콘텐츠와 기술·결정은 관심사가 달라 분리 효과가 있고, 병렬이면 시간이 합산되지 않는다.

## 5. 먼저 되돌릴 현재 잘못된 연결

### `backend/meetings/services.py`

현재 다시 추가된 아래 연결을 제거한다.

- `from meeting_analysis.node import run as analyze_meeting`
- `run_meeting_analysis()` 안의 `analyze_meeting(...)` 호출

대신 웹에서는 회의록 원문만 포함한 입력을 기획서 노드에 전달한다.

```python
structured_data = {
    "meeting_id": str(meeting.pk),
    "plan_source_text": meeting.content or "",
    "project": {},
    "users": [],
    "requirements": {},
    "decisions": [],
    "constraints": [],
    "unresolved": [],
}
```

중요: 이 빈 구조를 기존 `hybrid`에 넘기면 다시 모든 섹션이 비므로,
`plan_draft.agent.run()`의 원문 병렬 경로를 먼저 구현하거나 같은 변경 묶음에서 처리한다.

### 백엔드 테스트

`MeetingPlanPipelineTests.test_web_generation_passes_analysis_result_and_source_to_plan_node`
는 임시 구조화 재연결을 검증하려고 추가한 테스트다. 최종 구조에서는 삭제하거나
`analyze_meeting`이 호출되지 않고 원문이 `generate_plan`에 전달되는지를 검증하도록 바꾼다.

## 6. `ai/plan_draft` 구현 지침

### 6.1 응답 스키마

현재 사용할 수 있는 스키마:

- `context_writer.ContextPlan`: 1~4번
- `context_writer.FeaturePlan`: 5번
- `context_writer.TechnicalDecisionPlan`: 6~7번
- `context_writer.WholePlanDraft`: 1~7번 전체. 운영 경로에서는 사용하지 않는다.

호출 A용으로 다음과 같은 작은 스키마를 추가한다.

```python
class ContentPlanDraft(BaseModel):
    context: ContextPlan
    features: FeaturePlan
```

호출 B는 기존 `TechnicalDecisionPlan`을 사용한다.

### 6.2 프롬프트

호출 A 시스템 프롬프트:

- 원문만 최종 기준으로 사용
- 프로젝트 목적과 핵심 목표는 기능 나열이 아니어야 함
- 서비스의 주목적과 부가 목적을 구분
- 주요 기능은 사용자/운영자에게 제공되는 제품 능력만 포함
- 저장소·테이블·GPU·모델 학습은 주요 기능에서 제외
- evidence.quote는 원문의 연속 문자열 그대로 복사
- 미확정은 확정형으로 작성하지 않고 중요한 것만 review_questions로 이동

호출 B 시스템 프롬프트:

- 기술 현황, 확정된 기술 선택, 데이터 저장 방침, 제약을 구분
- 최종 결정은 명시적 합의와 후속 동의를 함께 읽음
- 회의 후반의 결정이 앞선 제안/미정 상태를 대체함
- `A 우선, 부족분은 B로 보완` 같은 구어체 합의를 범위 결정으로 보존
- 대표 용어 테이블과 동의어 매핑 테이블처럼 구성요소 역할을 생략하지 않음
- 제안·검토·질문은 최종 결정으로 올리지 않음
- 제외하기로 결정한 범위는 제외 결정으로 기록
- evidence.quote는 원문의 연속 문자열 그대로 복사

가능하면 `context_writer.py`의 기존 프롬프트 규칙을 재사용하되, 거대한
`WholePlanDraft`를 요구하지 않도록 A/B 전용 프롬프트 함수를 만든다.

### 6.3 `agent.run()`

`plan_source_text`가 있으면 운영 기본 경로는 다음이어야 한다.

```text
source 확인
  ├─ Future A: ContentPlanDraft 생성
  └─ Future B: TechnicalDecisionPlan 생성
병렬 완료
  ├─ 1~4 render_section
  ├─ 5 render_features
  └─ 6~7 render_technical_sections
reconcile_sections
PlanDocument 반환
```

필요한 context 로그 이름 예:

- `run content-plan proposal_id=...`
- `run technical-decisions proposal_id=...`

기존 `llm_instrumentation`이 호출별 시간·토큰·재시도를 자동 기록한다.

### 6.4 실험 경로

`indexed`, `direct`, `hybrid`가 평가용으로 남아 있어도 되지만 웹 기본 경로가
그 경로들에 의존해서는 안 된다. 가장 안전한 방식은 운영 기본 전략 이름을
`parallel`로 명시하고 기본값으로 두는 것이다.

```python
generation_strategy: Literal["parallel", "hybrid", "indexed", "direct"] = "parallel"
```

백엔드는 전략 인자를 넘기지 않으므로 기본값이 곧 운영 경로다.

## 7. 유지할 코드

다음은 삭제하거나 되돌리지 않는다.

- `ai/shared/llm_instrumentation.py`
- `_call()` 계측 연결
- 최근 1,000건 메모리 제한
- 재시도 실패 누적 토큰 집계
- `ai/plan_draft/quality_gate.py`
- `ai/tests/fixtures/plan_quality_golden.json`
- `ai/evaluate_plan_quality.py`
- `ai/compare_plan_strategies.py`
- 기존 근거 패널 frontend 변경
- 요구사항 정의서 하류 호환을 위한 `decisions.items`의 `[기능]`, `[기술]`, `[범위]` 태그 형식

## 8. 절대 금지 사항

- 전체 검수 LLM 추가 금지
- 사실 인덱스 LLM을 운영 경로에 다시 추가 금지
- 웹 기획서 생성에서 `meeting_analysis.node.run()` 호출 금지
- 모델 변경 금지
- `MAX_TOKENS`, `MAX_RETRIES`, reasoning effort 변경 금지
- 정규식으로 무신사·크림·유즈드 같은 특정 도메인 문구를 강제로 삽입 금지
- 골든 테스트를 통과시키기 위해 기대값을 낮추거나 삭제 금지
- 품질 기준을 통과하기 전에 평가서 작성 금지
- 한 번 실패했다고 아키텍처를 다시 변경 금지
- 관련 없는 backend/frontend 코드 수정 금지

## 9. 서비스 완료 기준

모두 충족해야 완료다.

### 차단 오류 0건

- 회의록에 없는 사실·기능 생성
- 제안·미결정을 최종 결정으로 승격
- 제외 기능을 주요 기능에 포함
- 최종 결정과 PM 확인 사항이 서로 모순
- 원문에 존재하지 않는 evidence.quote
- 7개 필수 섹션 누락
- 스키마 생성 실패
- 요구사항 정의서 생성 실패

### 정량 기준

- 중요한 기능·결정 회수율 전체 평균 90% 이상
- 각 회의록 최소 80% 이상
- 근거 일치율 100%
- 일반 회의록 180초 이내
- `meeting_musinsa_long.txt` 240초 이내
- 전체 자동 테스트 통과

### 무신사 장문 필수 4항목

`ai/tests/fixtures/plan_quality_golden.json`의 기준을 변경하지 않는다.

1. 핵심 목표: 트렌드 + 수명 주기 + 리세일/리셀
2. 최종 결정: 원본은 S3/오브젝트 스토리지, 핵심 서비스 데이터는 RDS
3. 최종 결정: 대표 용어 테이블과 동의어/유사어 매핑 테이블 연결
4. 최종 결정: 크림/KREAM 우선, 무신사 유즈드로 보완

금지 항목도 반드시 0건이어야 한다.

## 10. 테스트 순서

### 10.1 API 없는 테스트

```bash
cd /home/playdata/projects/SKN31-FINAL-1Team/ai
PYTHONPATH=. ../.venv/bin/pytest -q
```

백엔드:

```bash
cd /home/playdata/projects/SKN31-FINAL-1Team/backend
MYSQL_HOST= DJANGO_SETTINGS_MODULE=config.settings PYTHONPATH=../ai:. \
  ../.venv/bin/pytest -q meetings/tests.py
```

### 10.2 라이브 검증

API 호출은 코드와 단위 테스트가 모두 통과한 뒤 정확히 수행한다.

1. 짧거나 정리된 회의록 1건
2. `meeting_musinsa_long.txt` 1건

각 실행에서 기록할 값:

- 전체 `elapsed_seconds`
- 두 `llm_calls`의 `duration_seconds`
- `attempt_count`
- input/output/total tokens
- `required_recall`
- `missing_required`
- `matched_forbidden`
- `blocking_rule_issues`
- `passed`

`compare_plan_strategies.py`가 `parallel` 전략을 받을 수 있도록 선택지만 추가하되,
평가 기준은 수정하지 않는다.

### 10.3 하류 검증

- 생성된 `PlanDocument`로 요구사항 정의서 생성 테스트 실행
- 특히 `decisions.items` 태그가 유지되는지 확인
- 최종 결정의 범위 항목이 기능 요구사항으로 잘못 승격되지 않는지 확인

## 11. 작업 종료 보고 형식

다음만 보고한다.

1. 변경 파일과 변경 이유
2. 최종 운영 호출 구조와 호출 수
3. 단위/전체 테스트 결과
4. 짧은 회의록 실측 결과
5. 무신사 장문 실측 결과
6. 품질 기준별 통과/실패 표
7. 요구사항 정의서 하류 호환 결과
8. 남은 차단 오류가 있으면 완료라고 표현하지 말 것

## 12. 현재 주의사항

- 작업 트리는 이미 여러 사용자 변경과 이전 실험 변경이 섞인 dirty 상태다.
- `git reset --hard`, `git checkout --`, 광범위 revert 금지.
- 반드시 `git diff`를 확인하고 위 범위만 `apply_patch` 방식으로 수정한다.
- `ai/out/final_acceptance*`, `quality_compare*` 등 기존 실험 산출물을 삭제하지 않는다.
- 사용자가 작성한 frontend 및 다른 팀 backend 변경을 건드리지 않는다.

