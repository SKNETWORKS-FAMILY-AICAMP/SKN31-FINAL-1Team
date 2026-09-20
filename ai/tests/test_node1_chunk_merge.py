"""
노드 ① 청크 병합·중복 제거·길이 기준 분기 테스트.

2026-09-16: 짧은 회의록은 단일 호출, CHUNK_TRIGGER_CHARS를 넘는
회의록만 청크+병합으로 처리하도록 되돌렸다(node.py 모듈 docstring
"길이 기준 하이브리드로 재도입" 참고). 이 파일은 그 분기와, 병합 시
표현만 다른 중복을 유사도로 잡는 동작을 검증한다. 실제 LLM은 부르지
않는다 — client를 가짜로 채워 넣는다.
"""

from shared.schemas_base import Evidence

from meeting_analysis import node
from meeting_analysis.schemas import (
    Constraint,
    Decision,
    DecisionCategory,
    DecisionReconciliation,
    DecisionResolution,
    MeetingExtraction,
    Project,
    RequirementItem,
    Requirements,
)


def _project(name: str = "테스트") -> Project:
    return Project(
        name=name,
        background="",
        problem="",
        problem_items=[],
        goals=[],
        background_evidence=Evidence(quote="배경 근거 문장"),
        problem_evidence=Evidence(quote="문제 근거 문장"),
    )


def _extraction(decisions: list[Decision]) -> MeetingExtraction:
    return MeetingExtraction(
        project=_project(),
        users=[],
        requirements=Requirements(),
        scenarios=[],
        decisions=decisions,
        constraints=[],
        unresolved=[],
    )


def _decision(content: str, quote: str) -> Decision:
    return Decision(
        category=DecisionCategory.SCOPE,
        content=content,
        rationale="",
        evidence=Evidence(quote=quote),
    )


def test_is_duplicate_잡는_경우_어두_표현_차이():
    """'네.' 같은 어두 표현만 다른 문장은 중복으로 잡는다."""
    a = node._dedupe_key("스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.")
    b = node._dedupe_key("네. 스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.")

    assert node._is_duplicate(a, [b])


def test_is_duplicate_놓치는_경우_다른_단어():
    """완전히 다른 단어를 쓴 의미상 중복은 문자 유사도로 못 잡는다(알려진 한계)."""
    a = node._dedupe_key("원본은 S3에 저장한다")
    b = node._dedupe_key("원본 데이터는 오브젝트 스토리지에 적재한다")

    assert not node._is_duplicate(a, [b])


def test_is_duplicate_서로_다른_사실은_중복이_아니다():
    a = node._dedupe_key("무신사를 기준 소스로 삼는다")
    b = node._dedupe_key("유튜브 채널 40개를 트래킹한다")

    assert not node._is_duplicate(a, [b])


def test_is_duplicate_주체가_바뀌면_중복이_아니다():
    """
    2026-09-16: Codex가 재현한 사례의 회귀 테스트. "관리자는 회의록을
    삭제할 수 있다"와 "참여자는 회의록을 삭제할 수 있다"는 ratio가
    0.85로 높지만 권한 범위가 다른 별개 요구사항이라 병합하면 안 된다.
    """
    a = node._dedupe_key("관리자는 회의록을 삭제할 수 있다")
    b = node._dedupe_key("참여자는 회의록을 삭제할 수 있다")

    assert not node._is_duplicate(a, [b])


def test_merge_extractions_유사_표현_결정사항을_하나로_합친다():
    result = _extraction(
        [
            _decision(
                "스토리지랑 RDS를 나눠서 적재한다",
                "스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.",
            ),
            _decision(
                "스토리지랑 RDS를 나눠서 적재한다",
                "네. 스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.",
            ),
        ]
    )

    merged = node._merge_extractions([result], overview=result)

    assert len(merged["decisions"]) == 1


def test_merge_extractions_overview는_exhaustive_필드에_안_들어간다():
    """overview(전체 원문 통짜 호출)는 project·users 전용이다."""
    chunk_result = _extraction([_decision("청크 결정", "청크 원문 인용문장")])
    overview = _extraction(
        [_decision("오버뷰가 다시 서술한 같은 결정", "오버뷰 원문 인용문장")]
    )

    merged = node._merge_extractions([chunk_result], overview=overview)

    assert len(merged["decisions"]) == 1
    assert merged["decisions"][0]["content"] == "청크 결정"


def test_merge_extractions_결정전용결과가_청크의_제안과_중복을_대체한다():
    """전체 선후를 본 전용 결과가 있으면 청크의 중간 제안을 노출하지 않는다."""
    chunk_result = _extraction([
        _decision("공통 테이블 두 개를 추가한다", "테이블 두 개를 추가해 볼까요?"),
        _decision("원본은 S3에 저장한다", "원본은 S3에 저장하기로 했습니다."),
    ])
    final_decisions = [
        _decision(
            "사전 데이터는 카테고리별로 분리한다",
            "그럼 엔지니어가 말한 분리 방향으로 진행하는 걸로요.",
        ),
        _decision("원본은 S3에 저장한다", "원본은 S3에 저장하기로 했습니다."),
    ]

    merged = node._merge_extractions(
        [chunk_result],
        overview=chunk_result,
        reconciled_decisions=final_decisions,
    )

    assert [item["content"] for item in merged["decisions"]] == [
        "사전 데이터는 카테고리별로 분리한다",
        "원본은 S3에 저장한다",
    ]


def test_decision_candidates_요구사항과_전체개요의_결정도_후보로_보존한다():
    chunk = _extraction([_decision("청크 결정", "청크 결정으로 진행합니다.")])
    chunk.requirements.technical.append(
        RequirementItem(
            content="원본은 S3, 서비스 데이터는 RDS에 저장한다",
            evidence={"quote": "스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요."},
        )
    )
    overview = _extraction([_decision("전체 개요 결정", "전체 개요의 결정입니다.")])

    candidates = node._decision_candidates([chunk], overview)

    assert [item["content"] for item in candidates] == [
        "청크 결정",
        "원본은 S3, 서비스 데이터는 RDS에 저장한다",
        "전체 개요 결정",
    ]
    assert candidates[1]["category"] == "tech"
    assert candidates[1]["candidate_source"] == "requirements.technical"


def test_decision_candidates_기술제약도_실행환경_결정후보로_보존한다():
    chunk = _extraction([])
    chunk.constraints.append(Constraint(
        type="기술",
        content="RunPod 비용 때문에 학습 후 로컬 추론으로 이전한다",
        evidence=Evidence(
            quote="런팟은 비용이 계속 발생하니까 학습시킨 모델을 받아와서 로컬에서 사용하려고요."
        ),
    ))

    candidates = node._decision_candidates([chunk], _extraction([]))

    assert len(candidates) == 1
    assert candidates[0]["category"] == "tech"
    assert candidates[0]["candidate_source"] == "constraints[기술]"


class _FakeCompletions:
    def __init__(self, result: MeetingExtraction):
        self._result = result
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if kwargs.get("response_model") is DecisionReconciliation:
            return DecisionReconciliation(resolutions=[
                DecisionResolution(
                    candidate_ids=[index],
                    action="keep",
                    decision=decision,
                )
                for index, decision in enumerate(self._result.decisions, start=1)
            ])
        return self._result


class _FakeChat:
    def __init__(self, result: MeetingExtraction):
        self.completions = _FakeCompletions(result)


class _FakeClient:
    def __init__(self, result: MeetingExtraction):
        self.chat = _FakeChat(result)


class _StaticCompletions:
    def __init__(self, response):
        self.response = response

    def create(self, **kwargs):
        return self.response


class _StaticClient:
    def __init__(self, response):
        self.chat = type("Chat", (), {"completions": _StaticCompletions(response)})()


def test_reconcile_decisions_후보가_누락되면_원래결정을_모두_보존한다():
    candidates = [
        _decision("결정 A", "결정 A로 진행합니다.").model_dump(),
        _decision("결정 B", "결정 B로 진행합니다.").model_dump(),
    ]
    incomplete = DecisionReconciliation(resolutions=[
        DecisionResolution(
            candidate_ids=[1],
            action="keep",
            decision=_decision("결정 A", "결정 A로 진행합니다."),
        )
    ])

    reconciled = node._reconcile_decisions(
        _StaticClient(incomplete),
        candidates,
        "결정 A로 진행합니다. 결정 B로 진행합니다.",
        "",
    )

    assert [item["content"] for item in reconciled] == ["결정 A", "결정 B"]


def test_reconcile_decisions_실패시_요구사항에서_올린_후보는_확정하지_않는다():
    candidates = [
        _decision("확인된 결정", "확인된 결정입니다.").model_dump(),
        {
            **_decision("요구사항 후보", "검토 중인 요구사항입니다.").model_dump(),
            "candidate_source": "requirements.technical",
        },
    ]
    incomplete = DecisionReconciliation(resolutions=[])

    reconciled = node._reconcile_decisions(
        _StaticClient(incomplete), candidates, "회의록", ""
    )

    assert [item["content"] for item in reconciled] == ["확인된 결정"]


def test_reconcile_decisions_후보에_없는_인용이면_원래결정을_보존한다():
    candidates = [_decision("결정 A", "결정 A로 진행합니다.").model_dump()]
    invalid_quote = DecisionReconciliation(resolutions=[
        DecisionResolution(
            candidate_ids=[1],
            action="keep",
            decision=_decision("결정 A", "원문에 없는 새 인용"),
        )
    ])

    reconciled = node._reconcile_decisions(
        _StaticClient(invalid_quote),
        candidates,
        "결정 A로 진행합니다.",
        "",
    )

    assert reconciled == candidates


def test_reconcile_decisions_후보보다_짧아도_원문에_있는_인용은_허용한다():
    candidates = [
        _decision(
            "S3와 RDS를 분리한다",
            "원본은 S3에 저장하고 서비스 데이터는 RDS에 저장합니다.",
        ).model_dump()
    ]
    shortened = DecisionReconciliation(resolutions=[
        DecisionResolution(
            candidate_ids=[1],
            action="keep",
            decision=_decision(
                "S3와 RDS를 분리한다",
                "서비스 데이터는 RDS에 저장합니다.",
            ),
        )
    ])

    reconciled = node._reconcile_decisions(
        _StaticClient(shortened),
        candidates,
        "원본은 S3에 저장하고 서비스 데이터는 RDS에 저장합니다.",
        "",
    )

    assert reconciled[0]["evidence"]["quote"] == "서비스 데이터는 RDS에 저장합니다."


def test_reconcile_decisions_후보가_많으면_작은_묶음으로_나눈다(monkeypatch):
    monkeypatch.setattr(node, "DECISION_RECONCILE_BATCH_SIZE", 2)
    candidates = [
        _decision(f"결정 {index}", f"결정 {index}로 진행합니다.").model_dump()
        for index in range(1, 6)
    ]
    client = _StaticClient(None)
    batch_sizes: list[int] = []

    def fake_batch(_client, batch, _meeting_text, _glossary_text):
        batch_sizes.append(len(batch))
        return batch

    monkeypatch.setattr(node, "_reconcile_decision_batch", fake_batch)

    reconciled = node._reconcile_decisions(client, candidates, "회의록", "")

    assert sorted(batch_sizes) == [1, 2, 2]
    assert [item["content"] for item in reconciled] == [
        "결정 1", "결정 2", "결정 3", "결정 4", "결정 5",
    ]


def test_짧은_회의록은_단일_호출로_끝난다(monkeypatch):
    monkeypatch.setattr(node, "CHUNK_TRIGGER_CHARS", 100)
    result = _extraction([_decision("결정", "이것은 인용문입니다")])
    client = _FakeClient(result)

    text = "짧은 회의록" * 5  # 100자 이하
    assert len(text) <= 100

    structured = node._extract_structured(client, text, "")

    assert client.chat.completions.calls == 1
    assert structured["decisions"][0]["content"] == "결정"


def test_긴_회의록은_청크로_분할해_여러_번_호출한다(monkeypatch):
    monkeypatch.setattr(node, "CHUNK_TRIGGER_CHARS", 50)
    result = _extraction([_decision("결정", "이것은 인용문입니다")])
    client = _FakeClient(result)

    # chunk_meeting_text의 청크 상한(3,000자)을 넘겨 실제로 청크가
    # 2개 이상 나오게 문단을 충분히 많이 구성합니다.
    text = "\n\n".join(f"이것은 {i}번째 문단 내용입니다. " * 10 for i in range(30))
    assert len(text) > 3000

    node._extract_structured(client, text, "")

    # 청크별 호출(N) + 전체 개요(1) + 작은 결정 후보 정리(1) = N+2번 이상.
    assert client.chat.completions.calls >= 2
