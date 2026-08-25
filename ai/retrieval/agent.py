"""
b1_retrieval/agent.py

문서 임베딩·검색 파이프라인 (Qdrant)
LLM 생성 호출이 없는 유일한 에이전트 — 임베딩 모델 + 벡터 검색만 수행한다.
"""

import logging
from typing import Any, Dict, List

from .schemas import Chunk, SearchResult

logger = logging.getLogger(__name__)

COLLECTION_NAME = "documents"
CHUNK_SIZE_CHARS = 700       # 500~800자 권장, 문단 경계 우선
TOP_K = 5
SCORE_THRESHOLD = 0.7


def chunk_document(doc_id: str, title: str, text: str) -> List[Dict[str, Any]]:
    """TODO(담당자1): 문단 경계 우선 청크 분할 로직."""
    raise NotImplementedError


def embed_and_upsert(chunks: List[Dict[str, Any]]) -> None:
    """TODO(담당자1): 임베딩 모델 호출 -> Qdrant collection에 upsert."""
    # client = QdrantClient(...)
    # vectors = embedding_model.embed([c["text"] for c in chunks])
    # client.upsert(collection_name=COLLECTION_NAME, points=[...])
    raise NotImplementedError


def search(query: str, project_id: str, top_k: int = TOP_K) -> SearchResult:
    """
    TODO(담당자1): 질문을 임베딩 -> Qdrant search (payload filter: project_id)
    -> score_threshold 미만 제외 -> SearchResult로 반환
    """
    raise NotImplementedError
