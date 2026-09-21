# 기획서 생성 구조 변경 전 백업

작성일: 2026-09-20

이 문서는 6번 `기술 스택 및 제약사항`과 7번 `최종 결정사항`을 회의록
원문 기반으로 직접 생성하기 전 상태를 복구·비교하기 위한 백업 기록이다.

## 변경 전 생성 구조

1. `meeting_analysis.node.run`이 회의록을 구조화 JSON으로 변환한다.
2. 긴 회의록은 5,000자 청크와 전체 개요 호출로 분석한다.
3. 결정 후보는 청크의 decisions, data/technical requirements, 기술 제약에서
   수집한 뒤 최대 15개씩 병렬 정리한다.
4. `plan_draft.agent.run`은 원문이 있으면 1~5번을 GPT-5가 직접 작성한다.
5. 6번은 `list_builder.build_tech_scope`, 7번은
   `list_builder.build_decisions`가 구조화 배열을 코드로 조립한다.

## 변경 전 문제와 실제 확인 결과

- 같은 S3/RDS 방침이 기술·데이터 항목에 여러 번 반복됐다.
- RunPod 학습과 로컬 추론이 서로 다른 필드에 들어가 7번에서 누락됐다.
- 대표 용어/동의어 테이블 결정이 6번에는 있으나 7번에서 빠지는 실행이 있었다.
- 일반 기능, 현재 사용 도구, DB 필드가 최종 결정사항에 과잉 포함되는 실행이 있었다.
- 무신사 장문 회의록 실측 총 생성 시간은 약 203~371초로 편차가 컸다.

## 이 시점까지 수정된 주요 파일

- `ai/meeting_analysis/node.py`
- `ai/meeting_analysis/fact_check.py`
- `ai/meeting_analysis/prompts.py`
- `ai/meeting_analysis/prompt_templates/extraction.yaml`
- `ai/meeting_analysis/schemas.py`
- `ai/plan_draft/agent.py`
- `ai/plan_draft/context_writer.py`
- `ai/plan_draft/list_builder.py`
- `ai/plan_draft/prompt_templates/context_generation.yaml`
- 관련 `ai/tests/` 테스트

## 변경 전 검증 기준선

- 전체 AI 테스트: 393 passed, 2 skipped
- Python compileall 통과
- `git diff --check` 통과

## 복구 시 기준

새 원문 직접 작성 경로에 문제가 생기면 `plan_draft.agent.run`의 contextual
분기에서 기술·결정 전용 호출을 제거하고, `list_builder.build_all()` 결과의
`tech_scope`, `decisions`를 다시 사용하면 이 문서에 기록된 구조로 돌아간다.
기존 `list_builder` 경로는 삭제하지 않고 레거시 대체 경로로 보존한다.
