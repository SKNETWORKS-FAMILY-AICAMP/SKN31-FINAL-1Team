"""
노드 ② 기획서 생성 프롬프트 — 서술형 5개 섹션 전용.

## 최초 생성은 한 번에, 재생성은 섹션 단위로

서술형 5개는 지시가 거의 같습니다 — "구조화 JSON의 이 필드를 읽고 문단으로
풀어 써라". 다른 건 어느 필드를 쓰느냐뿐이라 매핑표 5줄이면 끝납니다.
섹션마다 나눠 부르면 구조화 JSON을 5번 다시 넣어야 해서 입력 토큰이
5배가 되고 지연 시간도 5배입니다.

반대로 반려 재생성은 반드시 섹션 단위로 합니다.
PM이 2번만 반려했는데 5개를 다 다시 만들면 손대지 않은 섹션 문장까지
바뀌어 "왜 다른 것도 바뀌었지?"가 됩니다.
"""

SYSTEM_PROMPT = """당신은 구조화된 회의 정보를 기획서 문서로 작성하는 편집자입니다.
새로운 정보를 추가하는 것이 아니라, 주어진 정보를 읽기 좋은 문서 형태로
다시 쓰는 것이 역할입니다.

## 담당 범위
아래 5개 섹션만 작성합니다. 다른 섹션은 시스템이 별도로 처리하므로
언급하거나 생성하지 마십시오.

  key=overview   프로젝트 개요   ← project.name + project.background
  key=problem    문제 정의       ← project.problem
  key=users      대상 사용자     ← users
  key=features   주요 기능       ← requirements.functional + decisions[category=feature]
  key=scenarios  사용자 시나리오 ← scenarios

## 절대 규칙
1. 입력 JSON에 없는 사실을 추가하지 마십시오.
   문장을 다듬는 것은 허용되지만, 없는 내용을 채우는 것은 금지입니다.
2. 지정된 원본 필드 외의 정보를 끌어와 쓰지 마십시오.
3. 원본 필드가 비어 있으면 content_html을 빈 문자열("")로 두십시오.
   추론해서 채우지 마십시오. 비어 있음을 표시하는 처리는 시스템이 합니다.
4. content_html은 <p>, <ul>, <li>, <strong> 태그만 사용합니다.
   style 속성, script, 인라인 CSS는 금지입니다.
5. evidence에는 그 섹션이 사용한 원본 항목의 quote를 그대로 옮겨 담으십시오.
   새로 만들지 마십시오.
6. 5개 섹션을 모두 출력하십시오. 내용이 없어도 key와 빈 content_html은
   포함해야 합니다.

## features(주요 기능) 작성 규칙
- 3~7개 항목으로 제한합니다.
- 사용자가 얻는 가치 기준으로 묶으십시오. 구현 단위로 나누지 마십시오.
- 각 항목은 30자 이내로 씁니다.
- 구현 방법, 기술 스택, 화면 구성은 언급하지 마십시오.
    O "회의록에서 기획서 자동 생성"
    X "LangGraph 노드로 회의록을 파싱하여 섹션별 HTML 생성"

## 문체
- 평서형 '~한다' 체를 사용합니다.
- 한 문단은 3문장 이내로 유지합니다."""


REGENERATE_PROMPT = """당신은 기획서의 서술형 섹션 하나만 다시 작성합니다.

## 입력
- 원본 구조화 JSON
- 재작성할 섹션의 key
- 검토자의 반려 유형과 반려 사유

## 규칙
1. 지정된 섹션 하나만 출력합니다. 다른 섹션은 건드리지 마십시오.
2. 반려 사유를 반영하되, 원본 JSON에 없는 사실은 여전히 추가할 수 없습니다.
3. 반려 사유가 "내용이 부족하다"인데 원본에 정보가 없다면,
   내용을 지어내지 말고 content_html을 빈 문자열로 두십시오.
   그 경우 시스템이 PM에게 직접 입력을 안내합니다.
4. 나머지 작성 규칙은 최초 생성과 동일합니다."""


def build_messages(structured: dict) -> list[dict]:
    """서술형 5개를 한 번에 생성하는 메시지."""
    import json

    # LLM에 넘길 필드만 추립니다.
    # 나열형 섹션이 쓰는 constraints 등은 넣지 않아 프롬프트를 가볍게 합니다.
    payload = {
        "project": structured.get("project"),
        "users": structured.get("users", []),
        "requirements": {
            "functional": structured.get("requirements", {}).get("functional", [])
        },
        "scenarios": structured.get("scenarios", []),
        "decisions": [
            d for d in structured.get("decisions", [])
            if d.get("category") == "feature"
        ],
    }
    return [{
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
    }]


def build_regenerate_messages(
    structured: dict, section_key: str, reject_type: str, comment: str
) -> list[dict]:
    """반려된 섹션 하나만 재생성하는 메시지."""
    import json

    return [{
        "role": "user",
        "content": (
            f"재작성할 섹션: {section_key}\n"
            f"반려 유형: {reject_type}\n"
            f"반려 사유: {comment}\n\n"
            f"[원본 구조화 JSON]\n"
            f"{json.dumps(structured, ensure_ascii=False, indent=2)}"
        ),
    }]
