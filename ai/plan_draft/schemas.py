"""
plan_draft/schemas.py

기획서 초안 화면의 출력 계약.

입력은 meeting_analysis 가 만든 PlanDraft(구조화 JSON)이고,
출력은 화면이 그대로 그릴 수 있는 12개 항목이다.

프론트엔드가 항목마다 다른 분기를 타지 않도록, 모든 내용을
블록(block) 이라는 공통 형태로 감싼다. 화면은 kind 만 보고
그리면 된다.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# 블록 — 화면이 그릴 수 있는 최소 단위
# --------------------------------------------------------------------------
class FieldBlock(Strict):
    """소제목 + 본문 문단. 1번 프로젝트 개요에 쓴다."""

    kind: Literal["field"] = "field"
    label: str
    text: str


class ListItem(Strict):
    """목록 한 줄. prefix 는 굵게 표시되는 앞머리."""

    prefix: str = ""
    text: str


class ListBlock(Strict):
    """제목이 붙은 목록. 2번, 3번, 5번, 11번에 쓴다."""

    kind: Literal["list"] = "list"
    heading: str = ""
    items: list[ListItem] = Field(default_factory=list)


class TableBlock(Strict):
    """표. 4번, 7~10번, 12번에 쓴다. rows 는 columns 와 길이가 같다."""

    kind: Literal["table"] = "table"
    heading: str = ""
    columns: list[str]
    rows: list[list[str]] = Field(default_factory=list)
    # 행마다 붙는 배지. 없으면 빈 문자열. 예: "핵심"
    badges: list[str] = Field(default_factory=list)


class FlowBlock(Strict):
    """단계 흐름 + 결과. 6번 사용자 시나리오에 쓴다."""

    kind: Literal["flow"] = "flow"
    heading: str = ""
    steps: list[str] = Field(default_factory=list)
    result: str = ""


class NoteBlock(Strict):
    """섹션 하단 안내 문구. 12번의 11장 참조 안내에 쓴다."""

    kind: Literal["note"] = "note"
    text: str


Block = Union[FieldBlock, ListBlock, TableBlock, FlowBlock, NoteBlock]


# --------------------------------------------------------------------------
# 섹션과 문서
# --------------------------------------------------------------------------
class SectionNo(int, Enum):
    OVERVIEW = 1
    PROBLEMS = 2
    GOALS = 3
    USERS = 4
    CORE_FEATURES = 5
    SCENARIOS = 6
    FUNCTIONAL = 7
    NON_FUNCTIONAL = 8
    DATA = 9
    TECHNICAL = 10
    SCOPE = 11
    DECISIONS = 12


class Section(Strict):
    """기획서 한 항목.

    is_empty 가 True 여도 섹션은 사라지지 않는다. 회의에서 논의되지
    않았다는 사실 자체가 사용자가 봐야 할 정보이기 때문이다.
    이때 화면은 blocks 대신 empty_message 를 표시한다.
    """

    no: int
    title: str
    is_empty: bool = False
    empty_message: str = ""
    blocks: list[Block] = Field(default_factory=list)


class DocumentHead(Strict):
    """문서 머리. 제목과 출처 회의 정보."""

    title: str
    meeting_title: str
    date: str
    participants: list[str] = Field(default_factory=list)


class TocEntry(Strict):
    no: int
    title: str
    is_empty: bool


class PlanDocument(Strict):
    """화면이 받는 최종 형태.

    evidence 는 이 구조에 포함되지 않는다. 근거는 검토·반려 판단과
    디버깅용이며 기획서 본문에 노출하지 않기로 정했다.
    """

    schema_version: Literal["1.1"] = SCHEMA_VERSION
    head: DocumentHead
    sections: list[Section]

    @property
    def toc(self) -> list[TocEntry]:
        return [
            TocEntry(no=s.no, title=s.title, is_empty=s.is_empty) for s in self.sections
        ]

    def section(self, no: int) -> Section:
        return next(s for s in self.sections if s.no == no)