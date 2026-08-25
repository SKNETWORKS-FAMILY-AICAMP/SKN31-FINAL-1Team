"""
graph_b.py

Track B(RAG 챗봇)는 Track A(graph.py)와 별개의 흐름이다.
문서 파이프라인처럼 회의록 등록 시 자동 실행되는 게 아니라,
사용자가 챗봇에 질문을 입력할 때마다 B1 -> B2 순으로 호출된다.
그래서 LangGraph의 State 그래프보다 단순한 함수 체인으로도 충분하지만,
LangSmith 트레이싱·재시도 정책을 Track A와 동일하게 가져가기 위해
동일한 방식으로 구성한다.
"""

from typing import Any, Dict

from b1_retrieval.agent import search
from b2_qa_answer.agent import qa_answer_node


def handle_chat_query(query: str, project_id: str) -> Dict[str, Any]:
    search_result = search(query=query, project_id=project_id)
    state = {"query": query, "chunks": [c.model_dump() for c in search_result.chunks]}
    return qa_answer_node(state)
