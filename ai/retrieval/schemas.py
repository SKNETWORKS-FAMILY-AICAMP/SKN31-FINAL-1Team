"""
b1_retrieval/schemas.py

컨텍스트 설계 요약
  - 입력: 저장된 문서 원문(회의록/기획서 등)
  - 처리: LLM 호출 없음 — 임베딩 모델 호출 + Qdrant upsert/search
  - Tools: 없음 (이 노드 자체가 검색 기능이므로 "tool을 호출"하는 게 아니라
           이 노드가 다음 노드(B2)에게 검색결과를 직접 전달함, State Passing)
  - 출력: 검색결과(청크) JSON
"""

from typing import List, Optional

from pydantic import BaseModel


class Chunk(BaseModel):
    chunk_id: str
    source_doc_id: str
    source_doc_title: str
    text: str
    score: float


class SearchResult(BaseModel):
    query: str
    chunks: List[Chunk]
