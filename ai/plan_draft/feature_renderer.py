"""
5번 주요 기능의 읽기용 HTML을 만듭니다.

## 소제목을 언제 붙이는가

기능이 확정 목록(mvp)과 목록과 별개로 확정된 연동(integration)으로
나뉘어 있을 때만 소제목을 붙입니다.

전부 한쪽에만 있으면 소제목 없이 예전처럼 평평하게 씁니다.
group 판정은 회의록에 여러 기능을 열거한 문장이 있을 때만 의미가
있는데(list_builder.decide_feature_groups 참고), 그런 문장이 없으면
모든 기능이 기본값 mvp가 됩니다. 그때 "MVP 기능 7개"라고 쓰면
회의에서 확정하지 않은 구분을 화면이 주장하게 됩니다.

## HTML 태그

프론트가 p, ul, li, strong만 렌더링하므로 그 범위 안에서 씁니다.
"""

from html import escape

# (group 값, 소제목, 세는 단위)
GROUP_LABELS = (
    ("mvp", "MVP 기능", "개"),
    ("integration", "별도 연동", "건"),
)


def _item_html(feature) -> str:
    return (
        f"<p><strong>{escape(feature.title)}</strong></p>"
        f"<p>{escape(feature.description)}</p>"
    )


def render_features(features) -> str:
    """기능 목록을 읽기용 HTML로 만듭니다."""
    if not features:
        return ""

    buckets = {
        group: [f for f in features if getattr(f, "group", "mvp") == group]
        for group, _, _ in GROUP_LABELS
    }

    filled = [group for group, items in buckets.items() if items]

    # 한 종류뿐이면 구분이 없는 것이므로 소제목을 붙이지 않습니다.
    if len(filled) < 2:
        return "".join(_item_html(f) for f in features)

    parts: list[str] = []

    for group, label, unit in GROUP_LABELS:
        items = buckets[group]

        if not items:
            continue

        parts.append(
            f"<p><strong>{label} {len(items)}{unit}</strong></p>"
        )
        parts.extend(_item_html(f) for f in items)

    return "".join(parts)