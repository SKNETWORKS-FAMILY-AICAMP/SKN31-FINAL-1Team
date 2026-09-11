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