# AI 에이전트 개발 디렉토리 구조

Track A(문서 생성 파이프라인)와 Track B(RAG 챗봇) 7개 에이전트의 실행 스켈레톤

## 구조

```
agents_project/
├── shared/                       # 공통 모듈
│   ├── llm_client.py              #   Instructor 클라이언트 생성
│   ├── retry_config.py            #   모델·재시도 기본값
│   └── schemas_base.py            #   공통 Enum (Priority, ReviewStatus, Source)
│
├── meeting_analysis/         # 회의록 AI 구조화 분석
├── plan_draft/               # 기획서 초안 생성
├── requirement_draft/        # 요구사항정의서 초안 생성
├── task_generation/          # 업무 자동 생성
├── assignee_recommend/       # AI 담당자 추천 (하이브리드: 규칙+LLM)
├── retrieval/                  # 문서 임베딩·검색 (Qdrant)
├── qa_answer/                  # RAG 질의응답 + 근거출처
│
├── graph.py                       # Track A 전체 파이프라인 조립 (반려 루프 포함)
├── graph_b.py                     # Track B 파이프라인 조립 (B1 -> B2)
├── state.py                       # Track A 파이프라인 공유 State
│
└── tests/
    ├── fixtures/                  #   테스트용 더미 데이터
    └── test_a2_1.py               #   스키마·프롬프트 조립 테스트
```

각 에이전트 폴더는 동일한 패턴을 따른다.

| 파일 | 역할 |
|---|---|
| `agent.py` | LangGraph 노드 진입점, 실행 로직 |
| `schemas.py` | 입출력 계약 (Pydantic) |
| `prompt_builder.py` | 고정 규칙(YAML) + 동적 데이터를 system prompt로 조립 |
| `prompts/*.yaml` | 역할·제약사항·few-shot (정적 자산) |

## 실행 준비

```bash
pip install instructor anthropic pydantic pyyaml langgraph pytest
export OPEN_API_KEY=...
python -m pytest tests/ -v
```
