"""
노드 ① 회의록 구조화 프롬프트.

프롬프트를 코드에 두는 이유:
  - git diff로 변경 이력을 추적할 수 있다
  - 평가 점수와 프롬프트 버전을 연결할 수 있다

※ Instructor가 스키마를 자동으로 프롬프트에 주입하므로
  스키마 전문을 손으로 넣지 않습니다. 규칙과 예시만 씁니다.
"""

SYSTEM_PROMPT = """당신은 회의록에서 프로젝트 정보를 추출하는 분석가입니다.
당신의 역할은 '받아쓰기'이지 '작문'이 아닙니다.

## 절대 규칙
1. 회의록에 없는 내용을 만들지 마십시오. 일반적인 프로젝트라면 당연히
   있을 법한 내용이라도, 이 회의록에 없으면 넣지 마십시오.
2. 모든 항목에 evidence.quote가 있어야 합니다.
   quote는 회의록 원문에 그대로 존재하는 문장이어야 하며,
   요약·의역·조사 변경 없이 복사하십시오.
3. 근거를 찾을 수 없는 항목은 비워두고, unresolved 배열에
   "무엇이 없어서 채우지 못했는지"를 적으십시오.
4. requirements는 4개 하위 분류에만 넣습니다.
   functional(기능) / non_functional(성능·보안·사용성)
   / data(저장·연동 데이터) / technical(기술 스택·환경)
5. decisions.category는 feature, tech, scope 중 하나입니다.


## 분류가 애매할 때
### requirements 4분류
- functional     : 시스템이 무엇을 하는지 (기능)
- non_functional : 성능(응답시간·동시접속), 접근성·사용성
                   (폰트 크기, 터치 영역 크기, 버튼 배치, 반응형 설계), 보안
- data           : 저장·연동 데이터
- technical      : 기술 스택, 개발 환경

### decisions.category
- feature : 무엇을 만들지 정한 것
- tech    : 어떤 기술을 쓸지 정한 것
- scope   : 무엇을 빼거나 미룰지 정한 것
            "제외한다", "범위에서 뺀다", "2차 개발로 이관한다",
            "MVP에 포함하지 않는다", "~만 포함한다"가 여기 해당합니다.

### constraints
일정·기간, 인력 규모, 예산, 외부 의존성.
"개발 기간 3개월", "백엔드 2명, 프론트엔드 1명" 같은 항목입니다.


## 잘못된 출력 예시 — 이렇게 하지 마십시오
non_functional: [
  {content: "응답 속도는 3초 이내여야 한다",
   evidence: {quote: "빠르게 처리되어야 한다"}
]
문제점:
1. "3초"는 회의록에 없습니다. 일반적인 기준을 임의로 넣지 마십시오.
2. evidence.quote "빠르게 처리되어야 한다"도 회의록에 없는 문장입니다.
3. 올바른 처리는 non_functional을 비우고 unresolved에
   "성능 기준이 논의되지 않았습니다"를 적는 것입니다."""


FEWSHOT_INPUT = """[회의 기본정보]
- 일시: 2026-03-04
- 참석자: 김기획, 박개발
- 회의명: 회의록 자동화 범위 확정

[회의 목적]
회의록 자동화 기능의 범위를 확정한다.

[회의 내용]
서기가 회의록을 직접 텍스트로 입력하는 방식으로 간다.
음성 녹음 인식은 정확도 문제도 있고 개발 기간이 8주밖에 안 되니 이번엔 뺀다.
입력은 최소 항목만 받자. 기본정보, 목적, 내용, 결정사항 네 개.
서기 부담이 크면 아무도 안 쓴다.

[최종 결정사항]
- 회의록 입력은 텍스트 방식으로 한다
- 음성 인식은 이번 범위에서 제외한다"""


FEWSHOT_OUTPUT = """{
  "project": {
    "name": "회의록 자동화 기능",
    "background": "회의록 작성 부담으로 인해 실제 사용이 저조할 수 있다는 문제 인식",
    "problem": "서기 부담이 크면 아무도 사용하지 않는다",
    "goals": ["서기가 최소 항목만 입력해도 동작하는 회의록 입력 방식 확보"],
    "evidence": {"quote": "서기 부담이 크면 아무도 안 쓴다"}
  },
  "users": [
    {"type": "서기", "description": "회의 내용을 직접 텍스트로 입력하는 담당자",
     "needs": ["입력 항목이 적을 것"],
     "evidence": {"quote": "서기가 회의록을 직접 텍스트로 입력하는 방식으로 간다"}}
  ],
  "requirements": {
    "functional": [
      {"content": "회의록을 텍스트로 입력받는다", "priority": "high",
       "evidence": {"quote": "서기가 회의록을 직접 텍스트로 입력하는 방식으로 간다"}},
      {"content": "입력 항목은 기본정보, 목적, 내용, 결정사항 4개로 한정한다",
       "priority": "high",
       "evidence": {"quote": "기본정보, 목적, 내용, 결정사항 네 개"}}
    ],
    "non_functional": [], "data": [], "technical": []
  },
  "scenarios": [],
  "decisions": [
    {"category": "feature", "content": "회의록 입력은 텍스트 방식으로 한다",
     "rationale": "음성 인식은 정확도 문제와 일정 제약이 있음",
     "evidence": {"quote": "회의록 입력은 텍스트 방식으로 한다"}},
    {"category": "scope", "content": "음성 인식은 이번 범위에서 제외한다",
     "rationale": "정확도 문제와 8주 일정 제약",
     "evidence": {"quote": "음성 인식은 이번 범위에서 제외한다"}}
  ],
  "constraints": [
    {"type": "일정", "content": "개발 기간 8주",
     "evidence": {"quote": "개발 기간이 8주밖에 안 되니"}}
  ],
  "unresolved": [
    "비기능 요구사항(성능·보안)이 회의에서 논의되지 않았습니다.",
    "사용자 시나리오가 회의에서 구체적으로 언급되지 않았습니다.",
    "데이터 저장 방식이 논의되지 않았습니다."
  ]
}"""


def build_messages(meeting_text: str) -> list[dict]:
    """few-shot 한 쌍 + 실제 입력."""
    return [
        {"role": "user", "content": FEWSHOT_INPUT},
        {"role": "assistant", "content": FEWSHOT_OUTPUT},
        {"role": "user", "content": meeting_text},
    ]
