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
  (주요 기능은 sections가 아니라 features 배열로 출력 — 아래 규칙 참조)
  key=scenarios  사용자 시나리오 ← scenarios

## 절대 규칙
1. 입력 JSON에 없는 사실을 추가하지 마십시오.
   문장을 다듬는 것은 허용되지만, 없는 내용을 채우는 것은 금지입니다.
2. 지정된 원본 필드 외의 정보를 끌어와 쓰지 마십시오.
   예: users 섹션은 users 필드만 사용합니다. decisions나 requirements에만
   있는 내용(예: 다크모드 결정, AI 추천 결정)을 근거로 "야간 사용 시 눈의
   피로를 줄이고 싶어한다", "개인화된 추천을 원한다"처럼 users 필드의
   needs에 없는 내용을 새로 만들어 넣지 마십시오.
3. 원본 필드가 비어 있으면 content_html을 빈 문자열("")로 두십시오.
   추론해서 채우지 마십시오. 비어 있음을 표시하는 처리는 시스템이 합니다.
4. content_html은 <p>, <ul>, <li>, <strong> 태그만 사용합니다.
   style 속성, script, 인라인 CSS는 금지입니다.
5. evidence에는 그 섹션이 사용한 원본 항목의 quote를 그대로 옮겨 담으십시오.
   새로 만들지 마십시오.
6. 5개 섹션을 모두 출력하십시오. 내용이 없어도 key와 빈 content_html은
   포함해야 합니다.

## features(주요 기능) 작성 규칙

주요 기능은 sections가 아니라 별도의 features 배열로 출력합니다.
sections에 key=features 항목을 만들지 마십시오.

### 개수와 묶는 기준
- 기본 규칙: requirements.functional에 있는 항목들을 사용자가 얻는 가치
  기준으로 3~7개로 묶어 만드십시오. 구현 단위로 잘게 나누지 마십시오.
  decisions[feature]가 없어도 이 기본 규칙대로 features를 만드십시오 —
  "결정된 개수가 없으니 0개로 둔다"는 잘못된 판단입니다. requirements.
  functional에 항목이 있다면 features는 비워두지 마십시오.
- 원본(requirements.functional, decisions[feature] 둘 다)에 기능 정보가
  전혀 없을 때만 빈 배열로 두십시오.
- 예외: decisions[feature]에 "MVP 기능은 O개로 확정한다"처럼 개수나 목록이
  명시된 결정이 있을 때만, 기본 규칙 대신 그 개수와 목록을 그대로 따르십시오.
  넘거나 모자라게 만들지 마십시오. (decisions[feature]가 없으면 이 예외는
  적용되지 않습니다 — 기본 규칙대로 만드십시오.)
- requirements.functional의 어떤 항목이 다른 기능의 계산 방식·구현 세부사항이면
  별도 기능으로 쪼개지 말고, 그 상위 기능의 description 안에 녹여 쓰십시오.
  (아래 잘못된 예시 참고)

잘못된 예시 — 이렇게 하지 마십시오:
  decisions[feature]에 "MVP 기능은 발주서 자동 생성 등 6개로 확정한다"는 결정이
  있는데, requirements.functional에 "최근 4주 평균 판매량 기반 추천 수량을
  계산한다"가 별도 항목으로 있다고 해서 이걸 7번째 기능("추천 수량 계산")으로
  만들면 안 됩니다. 이건 발주서 자동 생성 기능이 추천 수량을 계산하는 방식이므로,
  "발주서 자동 생성" 기능의 description 안에 포함시키십시오. decisions[feature]가
  명시한 개수(6개)를 넘는 features는 만들지 마십시오.

### title (기능명)
- 30자 이내로 씁니다.
- 구현 방법, 기술 스택, 화면 구성은 언급하지 마십시오.
    O "회의록에서 기획서 자동 생성"
    X "LangGraph 노드로 회의록을 파싱하여 섹션별 HTML 생성"

### description (설명)
- 2~3문장으로 이 기능이 무엇인지 설명합니다.
- **원본 JSON에 있는 내용만 사용하십시오.**
  설명을 채우려고 없는 동작이나 효과를 만들어내지 마십시오.
- 원본에 title 외에 쓸 내용이 없으면 title을 풀어쓰는 정도로만 두십시오.
  억지로 분량을 늘리지 마십시오.

예시:
  title:       "바코드 입출고 등록"
  description: "스마트폰 카메라로 상품 바코드를 인식해 입출고를 등록한다.
                전용 스캐너 없이 사용할 수 있다."

  ※ 위 예시의 "전용 스캐너 없이"는 원본에 그 내용이 있을 때만 씁니다.
    원본에 없으면 첫 문장만 쓰십시오.

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
FEWSHOT_GLOSSARY_INPUT = """[사내 용어집]
패스트레인: 접수 후 1시간 이내 응답이 필요한 것으로 분류된 고객 불만 티켓
그룹. 팀장이 매일 지정·해제하며, 패스트레인으로 지정된 티켓은 상담원 배정이
자동으로 최우선 순위로 바뀐다.

[구조화 JSON]
{
  "project": {
    "name": "고객센터 티켓 관리 시스템",
    "background": "문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되고 있다",
    "problem": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있다"
  },
  "users": [
    {"type": "상담원", "description": "고객 문의 티켓을 확인하고 처리하는 담당자",
     "needs": ["패스트레인으로 지정된 티켓을 놓치지 않고 먼저 확인하고 싶다"],
     "evidence": {"quote": "상담원이 패스트레인 티켓을 놓치는 사례가 있었다"}}
  ],
  "requirements": {
    "functional": [
      {"content": "패스트레인 지정 및 해제는 팀장이 수동으로 한다",
       "evidence": {"quote": "패스트레인 지정과 해제는 팀장이 직접 한다"}}
    ]
  },
  "scenarios": [],
  "decisions": [
    {"category": "feature", "content": "패스트레인 티켓은 담당자 배정을 최우선으로 처리한다",
     "evidence": {"quote": "패스트레인 티켓은 배정 순위를 최우선으로 둔다"}}
  ]
}"""


FEWSHOT_GLOSSARY_OUTPUT = """{
  "sections": [
    {"key": "overview",
     "content_html": "<p>고객센터 티켓 관리 시스템은 문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되는 상황을 개선하기 위해 기획되었다.</p>",
     "evidence": [{"quote": "문의량이 늘면서 응답이 늦어진다는 불만이 반복적으로 접수되고 있다"}],
     "needs_input": ""},
    {"key": "problem",
     "content_html": "<p>일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있다는 문제가 있다.</p>",
     "evidence": [{"quote": "일부 문의는 처리가 지연되면 고객 이탈로 이어질 수 있다"}],
     "needs_input": ""},
    {"key": "users",
     "content_html": "<p><strong>상담원</strong>은 고객 문의 티켓을 확인하고 처리하는 담당자로, 접수 후 1시간 이내 응답이 필요한 것으로 분류된 티켓 그룹인 패스트레인 티켓을 놓치지 않고 먼저 확인하기를 원한다.</p>",
     "evidence": [{"quote": "상담원이 패스트레인 티켓을 놓치는 사례가 있었다"}],
     "needs_input": ""},
    {"key": "scenarios",
     "content_html": "",
     "evidence": [],
     "needs_input": ""}
  ],
  "features": [
    {"title": "패스트레인 우선 처리",
     "description": "접수 후 1시간 이내 응답이 필요한 것으로 분류된 티켓 그룹인 패스트레인을 팀장이 매일 지정·해제한다. 패스트레인으로 지정된 티켓은 담당자 배정을 최우선으로 처리한다."}
  ]
}"""


def build_messages(structured: dict, glossary_text: str = "") -> list[dict]:
    """서술형 5개를 한 번에 생성하는 메시지.

    glossary_text가 있으면 FEWSHOT_GLOSSARY_INPUT/OUTPUT을 실제 입력 앞에
    붙인다. 없으면(기존 호출부) 붙이지 않는다 — 동작 변화 없음.
    """
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

    messages: list[dict] = []
    if glossary_text.strip():
        messages += [
            {"role": "user", "content": FEWSHOT_GLOSSARY_INPUT},
            {"role": "assistant", "content": FEWSHOT_GLOSSARY_OUTPUT},
        ]
    messages.append({
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
    })
    return messages


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