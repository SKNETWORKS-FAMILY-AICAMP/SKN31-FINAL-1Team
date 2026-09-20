"""
노드 1 회의록 구조화 프롬프트 연결 모듈.

실제 추출 규칙과 퓨샷 예시는 prompt_templates 디렉터리의
YAML 파일에서 관리합니다.

프롬프트 규칙:
    prompt_templates/extraction.yaml

퓨샷 예시:
    prompt_templates/extraction_fewshots.yaml

이 모듈은 기존 호출부가 사용하는 공개 이름을 유지합니다.

    SYSTEM_PROMPT
    build_system_prompt
    build_messages
"""

from .prompt_loader import (
    build_extraction_fewshot_messages,
    build_extraction_system_prompt,
)


SYSTEM_PROMPT = build_extraction_system_prompt()

DECISION_RECONCILIATION_RULES = """
청크별 분석이 찾은 결정 후보와 각 후보 주변의 원문 문맥을 시간 순서대로
검토하여 최종 결정 목록으로 정리합니다.

- 후보는 decisions뿐 아니라 requirements에서 회수한 항목도 포함합니다.
- 입력된 모든 candidate_id를 결과에 정확히 한 번 포함합니다. 누락하거나 중복하지 않습니다.
- 단순 제안, 질문, 검토 중인 선택지, 이미 철회된 방안은 action=drop으로 분류합니다.
- 회의 전에 이미 채택해 진행 중인 방식도, 대안 비교·비용 절감·저장 역할
  분리 같은 선택 이유가 확인되는 중요한 기술·데이터 아키텍처라면 keep합니다.
- 단순히 현재 쓰는 도구를 소개하거나 기존 기능의 동작을 설명한 것은
  기술 현황 또는 기능 요구사항이지 최종 결정사항이 아니므로 drop합니다.
- 같은 주제에서 여러 방안이 논의되면 마지막으로 합의된 결론만 남깁니다.
- 같은 최종 결정의 중간 제안과 최종 합의는 action=merge로 한 항목에 묶습니다.
- merge할 때 "그 방향", "그렇게", "엔지니어가 말한 방식" 같은 지시어만
  남기지 말고, 입력 후보에 있는 구체적인 대상·기술·저장 위치를 content에
  풀어서 씁니다.
- 독립적인 최종 결정은 action=keep으로 각각 유지합니다.
- 앞선 제안의 이유가 최종 결론을 설명하는 경우 rationale에 합치되, 원문에 없는 이유를 만들지 않습니다.
- 같은 최종 결정을 표현만 바꿔 두 번 작성하지 않습니다.
- 서로 다른 대상, 저장 위치, 운영 환경 또는 범위에 관한 결정은 각각 별도 항목으로 유지합니다.
- '진행하는 걸로', '이 방식으로', '그렇게 하자', '나눠서 적재', '우선 적용'처럼
  자연스러운 구어체 합의도 앞뒤 문맥상 합의가 분명하면 결정으로 추출합니다.
- '~하면 좋겠다', '~할 수 있다', 의문형 제안만 있고 동의나 채택이 없으면
  결정으로 만들지 않습니다. 반면 '~하려고 한다/계획했다'가 선택 가능한
  여러 후보 중 하나를 고민하는 말이 아니라 이미 정한 실행 계획을 설명하는
  문맥이면 keep합니다.
- 이미 구현을 끝냈는지가 아니라 회의에서 앞으로 따를 방안으로 합의됐는지를 판단합니다.
- 예: "RunPod에서 학습한 뒤 비용 때문에 로컬에서 추론한다"는 역할이 다른
  실행 환경을 정한 계획이므로, 기술 요구와 기술 제약 후보로 나뉘어 있어도
  하나의 구체적인 기술 결정으로 merge해 유지합니다.
- 예: "원본은 S3에 두고 서비스 데이터만 RDS에 적재한다"는 저장 역할을
  나눈 아키텍처 결정으로 유지합니다.
- keep/merge의 decision.evidence.quote는 입력 후보 중 최종 합의를 가장 직접적으로
  보여주는 quote 하나를 글자 그대로 사용합니다. drop이면 decision은 null입니다.
""".strip()


def build_system_prompt(glossary_text: str = "") -> str:
    """
    회의록 구조화 시스템 프롬프트를 반환합니다.

    용어집이 전달되면 기본 추출 규칙 뒤에 용어집 사용 규칙과
    용어집 내용을 추가합니다.

    용어집은 표현을 해석하는 참고 자료일 뿐이며,
    회의록에 없는 내용을 새로 만드는 근거로 사용할 수 없습니다.
    """
    if not glossary_text.strip():
        return SYSTEM_PROMPT

    return "\n\n".join(
        [
            SYSTEM_PROMPT,
            (
                "사내 용어집\n"
                "아래 용어집은 회의록의 사내 용어와 약어를 해석할 때만 "
                "참고하십시오.\n"
                "용어집에만 있고 회의록 원문에 없는 내용을 추출하거나 "
                "근거로 사용하지 마십시오.\n"
                "evidence.quote에는 반드시 회의록 원문에 실제로 존재하는 "
                "문장만 작성하십시오.\n\n"
                f"{glossary_text.strip()}"
            ),
        ]
    )


def build_decision_system_prompt(glossary_text: str = "") -> str:
    """청크가 찾은 결정 후보를 최종 상태로 정리하는 시스템 프롬프트."""
    return "\n\n".join([
        build_system_prompt(glossary_text),
        "결정사항 전용 최종 정리 규칙",
        DECISION_RECONCILIATION_RULES,
    ])


def build_messages(meeting_text: str) -> list[dict]:
    """
    퓨샷 예시와 실제 회의록 입력을 메시지 배열로 구성합니다.

    시스템 프롬프트는 node.py에서 별도로 전달하므로
    이 함수에서는 user와 assistant 메시지만 반환합니다.
    """
    if not isinstance(meeting_text, str):
        raise TypeError("meeting_text는 문자열이어야 합니다.")

    if not meeting_text.strip():
        raise ValueError("meeting_text가 비어 있습니다.")

    messages = build_extraction_fewshot_messages()

    messages.append(
        {
            "role": "user",
            "content": meeting_text.strip(),
        }
    )

    return messages
