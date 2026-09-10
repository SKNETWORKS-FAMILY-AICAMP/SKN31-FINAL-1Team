"""
노드 ② 기획서 생성 프롬프트.

## 최초 생성은 한 번에, 재생성은 섹션 단위로

프로젝트 개요, 문제 정의, 대상 사용자는 서술형으로 작성합니다.
주요 기능은 편집 가능한 배열로 생성합니다.
프로젝트 목표는 노드 1의 목표가 없을 때만 보완하여 생성합니다.
이 결과들은 한 번의 호출로 생성하여 입력 토큰과 호출 지연을 줄입니다.

반대로 반려 재생성은 반드시 섹션 단위로 합니다.
PM이 2번만 반려했는데 5개를 다 다시 만들면 손대지 않은 섹션 문장까지
바뀌어 "왜 다른 것도 바뀌었지?"가 됩니다.
"""

SYSTEM_PROMPT = """당신은 구조화된 회의 정보를 기획서 문서로 작성하는 편집자입니다.

주어진 구조화 JSON에 있는 정보만 사용하여 기획서를 작성합니다.
새로운 사실을 추가하거나 근거가 없는 내용을 추론하지 마십시오.

## 출력 구조

응답은 sections, goals, features로 구성합니다.

sections 배열에는 다음 3개 서술형 섹션만 작성합니다.

key=overview
프로젝트 개요입니다.
project.name과 project.background만 사용합니다.

key=problem
문제 정의입니다.
project.problem만 사용합니다.

key=users
대상 사용자입니다.
users만 사용합니다.

goals 배열에는 프로젝트 목표를 작성합니다.
단, project.goals가 비어 있을 때만 작성합니다.

features 배열에는 주요 기능을 작성합니다.

프로젝트 목표, 주요 기능, 기술 스택 및 제약사항, 최종 결정사항을
sections 배열에 넣지 마십시오.

## 공통 규칙

1. 입력 JSON에 없는 사실을 추가하지 마십시오.

2. 각 출력 항목은 지정된 원본 필드만 사용하십시오.

3. 원본 정보가 비어 있으면 내용을 추론해서 채우지 마십시오.

4. content_html에는 p, ul, li, strong 태그만 사용할 수 있습니다.

5. style 속성, script, 인라인 CSS는 사용하지 마십시오.

6. evidence의 quote는 입력 JSON에 있는 quote를 글자 그대로 복사하십시오.

7. evidence 문장을 요약하거나 문장 표현을 수정하지 마십시오.

8. sections 배열에는 overview, problem, users를 모두 출력하십시오.

9. 서술형 섹션의 원본 정보가 없으면 content_html을 빈 문자열로 두십시오.

10. 내용이 없는 서술형 섹션도 key와 빈 content_html을 포함하십시오.

11. goals와 features는 sections 배열에 넣지 마십시오.

12. 문장은 평서형인 '한다' 체로 작성하십시오.

13. 한 문단은 3문장 이내로 작성하십시오.

## 프로젝트 개요 작성 규칙

1. project.name과 project.background만 사용하십시오.

2. 프로젝트가 시작된 배경을 읽기 쉬운 문단으로 작성하십시오.

3. project.problem, requirements, decisions의 내용을 가져오지 마십시오.

4. 프로젝트의 기대 효과나 성과를 임의로 추가하지 마십시오.

## 문제 정의 작성 규칙

1. project.problem만 사용하십시오.

2. 프로젝트에서 해결하려는 문제를 명확한 문장으로 작성하십시오.

3. 문제의 원인이나 영향을 입력에 없는 내용으로 확장하지 마십시오.

4. 기능이나 해결 방법을 문제 정의에 추가하지 마십시오.

## 대상 사용자 작성 규칙

1. users만 사용하십시오.

2. 각 사용자의 type, description, needs를 바탕으로 작성하십시오.

3. 사용자가 여러 명이면 사용자별로 구분하여 작성하십시오.

4. requirements나 decisions에만 있는 내용을 사용자의 요구로 추가하지 마십시오.

5. 사용자의 요구가 입력에 없으면 임의로 만들어내지 마십시오.

## 프로젝트 목표 생성 규칙

1. project.goals에 항목이 하나라도 있으면 goals를 빈 배열로 출력하십시오.

2. project.goals가 비어 있을 때만 goals를 생성하십시오.

3. 목표 생성에는 다음 필드만 사용할 수 있습니다.

project.background
project.problem
requirements.functional
feature 범주의 decisions

4. 목표는 기능 자체가 아니라 기능을 통해 해결하거나 개선하려는 상태로 작성하십시오.

5. 목표는 최소 1개, 최대 3개까지 생성하십시오.

6. 목표를 뒷받침하는 정보가 부족하면 goals를 빈 배열로 출력하십시오.

7. 각 목표는 한 문장으로 작성하십시오.

8. 각 목표 문장은 평서형인 '한다'로 끝내십시오.

9. 서로 같은 의미의 목표는 하나로 합치십시오.

10. 기능 요구사항을 그대로 복사하여 목표로 사용하지 마십시오.

11. 입력에 없는 수치, 성과, 사용자 요구 또는 사업 효과를 추가하지 마십시오.

12. 기술 스택, 일정, 담당자 또는 작업 기한만으로 목표를 만들지 마십시오.

13. 각 목표에는 목표 생성에 사용한 evidence를 하나 이상 포함하십시오.

14. evidence의 quote는 입력 JSON에 존재하는 quote를 글자 그대로 복사하십시오.

15. 입력 JSON에서 확인할 수 없는 quote를 생성하지 마십시오.

## 주요 기능 작성 규칙

주요 기능은 sections가 아니라 features 배열로 출력합니다.
sections 배열에 key=features 항목을 만들지 마십시오.

1. requirements.functional과 feature 범주의 decisions만 사용하십시오.

2. requirements.functional에 기능 정보가 있으면 features를 비워두지 마십시오.

3. 기능 정보가 전혀 없을 때만 features를 빈 배열로 출력하십시오.

4. 기능은 사용자가 얻는 가치를 기준으로 묶으십시오.

5. 구현 단위나 세부 계산 방식을 별도 기능으로 나누지 마십시오.

6. 다른 기능의 구현 방법이나 세부 동작은 해당 기능의 description에 포함하십시오.

7. 원본에 기능이 충분한 경우 3개에서 7개 범위로 정리하십시오.

8. 원본 기능이 3개보다 적으면 개수를 억지로 늘리지 마십시오.

9. features는 최대 7개를 넘지 마십시오.

10. feature 범주의 decisions에 기능의 개수나 목록이 명시되어 있으면 해당 결정을 따르십시오.

11. 기능 개수나 목록에 대한 결정이 없으면 requirements.functional을 기준으로 구성하십시오.

## 주요 기능 title 작성 규칙

1. title은 30자 이내로 작성하십시오.

2. 사용자가 이해할 수 있는 기능명으로 작성하십시오.

3. 구현 방법, 기술 스택 또는 내부 처리 구조를 기능명에 넣지 마십시오.

4. 입력에 없는 기능을 새로 만들지 마십시오.

## 주요 기능 description 작성 규칙

1. 기능이 무엇인지 1문장에서 3문장으로 설명하십시오.

2. requirements.functional과 feature 범주의 decisions에 있는 내용만 사용하십시오.

3. 기능 설명을 채우기 위해 입력에 없는 동작이나 효과를 추가하지 마십시오.

4. 상세 정보가 부족하면 기능명을 자연스럽게 풀어 쓰는 정도로 작성하십시오.

5. 같은 내용을 반복해서 분량을 늘리지 마십시오.
"""


REGENERATE_PROMPT = """당신은 기획서의 서술형 섹션 하나만 다시 작성합니다.

## 입력
- 원본 구조화 JSON
- 재작성할 섹션의 key
- 검토자의 반려 유형과 반려 사유

## 규칙
1. 지정된 섹션 하나만 출력합니다. 다른 섹션은 건드리지 마십시오.
2. 반려 사유를 반영하되, 원본 JSON에 없는 사실은 여전히 추가할 수 없습니다.
3. 나머지 작성 규칙은 최초 생성과 동일합니다.

## 반려 사유를 다 반영할 수 없을 때

원본 JSON에 없는 정보를 요구받는 경우가 있습니다.
예를 들어 "구체적인 수치를 넣어달라"고 했는데 원본에 수치가 없는 경우입니다.

이때 수치를 지어내지 마십시오. 대신 아래 세 가지로 나누어 처리합니다.

가) 반려 사유를 전부 반영할 수 있다
    → content_html을 다시 쓰고, needs_input은 빈 문자열로 둡니다.

나) 일부만 반영할 수 있다
    → 반영 가능한 만큼만 content_html에 쓰고,
      needs_input에 반영하지 못한 부분과 그 이유를 적습니다.
    예: "구체적인 수치는 원본에 없어 포함하지 못했습니다."

다) 전혀 반영할 수 없다
    → content_html은 기존 내용을 그대로 유지하고,
      needs_input에 무엇이 필요한지 적습니다.
    예: "성능 목표치가 회의에서 논의되지 않아 이 요청을 반영할 수 없습니다."

**같은 내용을 길게 늘여 쓰는 것으로 반려 사유를 반영한 척하지 마십시오.**
문장을 반복하거나 표현만 바꿔 분량을 늘리는 것은 반영이 아닙니다.
그런 경우는 나) 또는 다)에 해당합니다.

needs_input은 작성자에게 그대로 보여집니다.
"어떤 정보가 있으면 채울 수 있는지"를 한 문장으로 적으십시오."""


def build_system_prompt(glossary_text: str = "") -> str:
    """SYSTEM_PROMPT + (있다면) 사내 용어집 섹션을 붙여서 반환한다.

    meeting_analysis/prompts.py의 build_system_prompt와 동일한 패턴.
    구조화 JSON 안에 "핫존"처럼 정의 없는 사내 용어가 고유명사로 남아있으면,
    node①은 그걸 그대로 옮겨 담기만 하면 되지만 node②는 문장으로 풀어
    써야 하므로(예: "핫존에는 ~") 뜻을 모르면 설명을 생략하거나 지어낼
    위험이 node①보다 더 큽니다 — 그래서 여기도 동일하게 주입합니다.
    """
    if not glossary_text.strip():
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + "\n\n## 사내 용어집 (절대 규칙 1·2의 예외)\n"
        "아래는 이 회사/팀에서 쓰는 용어와 그 의미입니다. 원본 JSON에 이 "
        "용어가 나오면, 정의를 반영해 그 용어가 무엇인지 자연스러운 문장으로 "
        "함께 설명하십시오 — 이건 절대 규칙 1·2가 금지하는 '새로운 사실 "
        "추가'가 아닙니다. 용어의 뜻을 정확히 전달하는 것도 이 문서의 역할이며, "
        "정의를 무시하고 용어만 반복하는 것이 오히려 더 나쁜 처리입니다. "
        "(용어집에 없는 용어의 뜻은 여전히 지어내지 마십시오 — 이건 그대로입니다.)\n\n"
        "예: 원본에 \"핫존 지정 및 해제는 영업 담당자가 매주 갱신한다\"가 있고, "
        "용어집에 \"핫존: 유동인구가 많아 배포 효율이 높은 구역\"이 있으면\n"
        "  나쁜 예: \"영업 담당자가 핫존을 지정·해제합니다\" "
        "(정의를 무시하고 용어만 반복 — 하지 마십시오)\n"
        "  좋은 예: \"영업 담당자가 유동인구가 많아 배포 효율이 높은 구역인 "
        "핫존을 매주 지정·해제합니다\" (정의를 반영해 풀어 씀)\n\n"
        f"{glossary_text.strip()}"
    )


# 용어집 few-shot 전용 예시.
#
# build_system_prompt만으로(글로 된 규칙 + 예외 명시 + 좋은예/나쁜예) 두 번
# 시도했으나 둘 다 핫존을 정의 없이 그대로 반복하기만 했다 — "절대 규칙
# 1·2에 없는 사실을 추가하지 말라"는 지시가 뒤에 붙은 용어집 예외 설명보다
# 더 강하게 작동하는 것으로 보인다. node①에서도 프롬프트 글만으로는 규칙
# 6번(결정+유보 혼재 문장)이 반영되지 않다가 실제 입출력 예시(FEWSHOT_INPUT_2)를
# 추가하고서야 반영된 전례가 있다 — 같은 패턴이라 여기도 few-shot으로 간다.
#
# 실제 테스트 픽스처(hotzone_test.txt, 핫존)와 다른 도메인(고객센터 티켓
# 관리, 패스트레인)을 쓴다. 같은 도메인이면 모델이 규칙을 일반화하지 않고
# "핫존"이라는 표면적인 글자만 패턴매칭할 위험이 있기 때문 — node①의
# FEWSHOT_INPUT_2가 배송비 정책이라는 별도 도메인을 쓴 이유와 동일하다.
#
# 용어집 정의는 실제 호출에서는 시스템 프롬프트(build_system_prompt)에
# 들어가지만, 이 few-shot 예시의 가상 용어(패스트레인)는 실제 용어집에
# 없으므로 이 예시 자체의 user 메시지 안에 [사내 용어집] 블록으로 직접
# 넣어준다 — 그래야 모델이 "이 예시에서 어떤 정의를 보고 어떻게 반영했는지"를
# 학습할 수 있다.
# 프로젝트 목표 보완 동작을 학습시키는 예시입니다.
# 실제 입력과 다른 휴가 관리 도메인을 사용합니다.
FEWSHOT_GOAL_INPUT = """{
  "project": {
    "name": "사내 휴가 신청 시스템",
    "background": "휴가 신청을 이메일로 접수하고 있어 신청 형식이 일정하지 않다",
    "problem": "반차 신청에서 오전과 오후 구분이 누락되는 사례가 반복되고 있다",
    "goals": [],
    "background_evidence": {
      "quote": "휴가 신청을 이메일로 접수하고 있어 신청 형식이 일정하지 않습니다."
    },
    "background_evidence_status": "verified",
    "problem_evidence": {
      "quote": "반차 신청에서 오전과 오후 구분이 누락되는 사례가 반복되고 있습니다."
    },
    "problem_evidence_status": "verified"
  },
  "users": [],
  "requirements": {
    "functional": [
      {
        "content": "휴가 신청 화면에서 오전 반차와 오후 반차를 선택할 수 있게 한다",
        "evidence": {
          "quote": "휴가 신청 화면에 오전 반차와 오후 반차 선택 항목을 추가합니다."
        },
        "evidence_status": "verified"
      }
    ]
  },
  "decisions": [
    {
      "category": "feature",
      "content": "반차 유형 선택 기능을 추가한다",
      "rationale": null,
      "evidence": {
        "quote": "반차 유형 선택 기능은 이번 개발 범위에 포함하기로 했습니다."
      },
      "evidence_status": "verified"
    }
  ]
}"""


FEWSHOT_GOAL_OUTPUT = """{
  "sections": [
    {
      "key": "overview",
      "content_html": "<p>사내 휴가 신청 시스템은 휴가 신청을 이메일로 접수하여 신청 형식이 일정하지 않은 상황을 개선하기 위해 기획되었다.</p>",
      "evidence": [
        {
          "quote": "휴가 신청을 이메일로 접수하고 있어 신청 형식이 일정하지 않습니다."
        }
      ],
      "needs_input": ""
    },
    {
      "key": "problem",
      "content_html": "<p>반차 신청 과정에서 오전과 오후 구분이 누락되는 사례가 반복되고 있다.</p>",
      "evidence": [
        {
          "quote": "반차 신청에서 오전과 오후 구분이 누락되는 사례가 반복되고 있습니다."
        }
      ],
      "needs_input": ""
    },
    {
      "key": "users",
      "content_html": "",
      "evidence": [],
      "needs_input": ""
    }
  ],
  "goals": [
    {
      "content": "반차 유형을 선택할 수 있게 하여 휴가 신청 정보의 누락을 줄인다.",
      "evidence": [
        {
          "quote": "반차 신청에서 오전과 오후 구분이 누락되는 사례가 반복되고 있습니다."
        },
        {
          "quote": "휴가 신청 화면에 오전 반차와 오후 반차 선택 항목을 추가합니다."
        }
      ]
    }
  ],
  "features": [
    {
      "title": "반차 유형 선택",
      "description": "휴가 신청 화면에서 오전 반차와 오후 반차를 선택할 수 있다."
    }
  ]
}"""


# 용어집이 제공됐을 때 용어의 정의를 문서에 반영하는 방법을 보여주는 예시입니다.
FEWSHOT_GLOSSARY_INPUT = """[사내 용어집]
패스트레인: 접수 후 1시간 이내 응답이 필요한 것으로 분류된 고객 불만 티켓 그룹. 팀장이 매일 지정하거나 해제하며, 패스트레인으로 지정된 티켓은 상담원 배정 순위가 가장 높아진다.

[구조화 JSON]
{
  "project": {
    "name": "고객센터 티켓 관리 시스템",
    "background": "문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되고 있다",
    "problem": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있다",
    "goals": [],
    "background_evidence": {
      "quote": "문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되고 있습니다."
    },
    "background_evidence_status": "verified",
    "problem_evidence": {
      "quote": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있습니다."
    },
    "problem_evidence_status": "verified"
  },
  "users": [
    {
      "type": "상담원",
      "description": "고객 문의 티켓을 확인하고 처리하는 담당자",
      "needs": [
        "패스트레인으로 지정된 티켓을 놓치지 않고 먼저 확인하고 싶다"
      ],
      "evidence": {
        "quote": "상담원이 패스트레인 티켓을 놓치는 사례가 있었습니다."
      },
      "evidence_status": "verified"
    }
  ],
  "requirements": {
    "functional": [
      {
        "content": "패스트레인 지정 및 해제는 팀장이 수동으로 한다",
        "evidence": {
          "quote": "패스트레인 지정과 해제는 팀장이 직접 합니다."
        },
        "evidence_status": "verified"
      }
    ]
  },
  "decisions": [
    {
      "category": "feature",
      "content": "패스트레인 티켓은 담당자 배정을 최우선으로 처리한다",
      "rationale": null,
      "evidence": {
        "quote": "패스트레인 티켓은 배정 순위를 최우선으로 둡니다."
      },
      "evidence_status": "verified"
    }
  ]
}"""


FEWSHOT_GLOSSARY_OUTPUT = """{
  "sections": [
    {
      "key": "overview",
      "content_html": "<p>고객센터 티켓 관리 시스템은 문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되는 상황을 개선하기 위해 기획되었다.</p>",
      "evidence": [
        {
          "quote": "문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되고 있습니다."
        }
      ],
      "needs_input": ""
    },
    {
      "key": "problem",
      "content_html": "<p>일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있다는 문제가 있다.</p>",
      "evidence": [
        {
          "quote": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있습니다."
        }
      ],
      "needs_input": ""
    },
    {
      "key": "users",
      "content_html": "<p><strong>상담원</strong>은 고객 문의 티켓을 확인하고 처리하는 담당자이며, 접수 후 1시간 이내 응답이 필요한 고객 불만 티켓 그룹인 패스트레인을 놓치지 않고 먼저 확인하기를 원한다.</p>",
      "evidence": [
        {
          "quote": "상담원이 패스트레인 티켓을 놓치는 사례가 있었습니다."
        }
      ],
      "needs_input": ""
    }
  ],
  "goals": [
    {
      "content": "우선 처리가 필요한 문의의 처리 지연을 줄여 고객 이탈 위험을 낮춘다.",
      "evidence": [
        {
          "quote": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있습니다."
        },
        {
          "quote": "패스트레인 티켓은 배정 순위를 최우선으로 둡니다."
        }
      ]
    }
  ],
  "features": [
    {
      "title": "패스트레인 우선 처리",
      "description": "팀장은 접수 후 1시간 이내 응답이 필요한 고객 불만 티켓 그룹인 패스트레인을 지정하거나 해제할 수 있다. 패스트레인 티켓은 담당자 배정 순위를 가장 높게 처리한다."
    }
  ]
}"""


def build_messages(
    structured: dict,
    glossary_text: str = "",
) -> list[dict]:
    """
    서술형 3개 섹션, 조건부 프로젝트 목표와 주요 기능을 생성합니다.

    프로젝트 목표 보완 예시는 모든 호출에 포함합니다.
    용어집 예시는 실제 용어집이 제공된 경우에만 포함합니다.
    """
    import json

    requirements = structured.get("requirements") or {}

    payload = {
        "project": structured.get("project") or {},
        "users": structured.get("users", []),
        "requirements": {
            "functional": requirements.get("functional", []),
        },
        "decisions": [
            decision
            for decision in structured.get("decisions", [])
            if decision.get("category") == "feature"
        ],
    }

    messages: list[dict] = [
        {
            "role": "user",
            "content": FEWSHOT_GOAL_INPUT,
        },
        {
            "role": "assistant",
            "content": FEWSHOT_GOAL_OUTPUT,
        },
    ]

    if glossary_text.strip():
        messages.extend(
            [
                {
                    "role": "user",
                    "content": FEWSHOT_GLOSSARY_INPUT,
                },
                {
                    "role": "assistant",
                    "content": FEWSHOT_GLOSSARY_OUTPUT,
                },
            ]
        )

    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
        }
    )

    return messages


def build_regenerate_messages(
    structured: dict,
    section_key: str,
    reject_type: str,
    comment: str,
) -> list[dict]:
    """
    반려된 서술형 섹션 하나를 재생성하기 위한 메시지를 만듭니다.

    현재 agent.py의 기존 호출 형태를 유지하기 위해 남겨두는 함수입니다.
    """
    import json

    requirements = structured.get("requirements") or {}

    payload = {
        "structured": {
            "project": structured.get("project") or {},
            "users": structured.get("users", []),
            "requirements": {
                "functional": requirements.get("functional", []),
            },
            "decisions": [
                decision
                for decision in structured.get("decisions", [])
                if decision.get("category") == "feature"
            ],
        },
        "section_key": section_key,
        "reject_type": reject_type,
        "comment": comment,
    }

    return [
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
        }
    ]