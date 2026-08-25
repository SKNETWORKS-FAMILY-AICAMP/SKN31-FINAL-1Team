"""
b2_qa_answer/schemas.py

컨텍스트 설계 요약
  - 입력: 사용자 질문 + B1 검색결과(청크), State Passing (B1이 직접 전달)
  - 정적 참고자료: "청크 안에서만 답하라" few-shot
  - Tools: 없음 (검색은 B1이 미리 수행 — B2는 검색결과를 직접 전달받아 답변만 생성)
  - 출력: 답변 + 출처 JSON
"""

from typing import List

from pydantic import BaseModel


class SourceRef(BaseModel):
    source_doc_id: str
    source_doc_title: str
    chunk_id: str


class Answer(BaseModel):
    query: str
    answer: str
    sources: List[SourceRef]
    has_evidence: bool
