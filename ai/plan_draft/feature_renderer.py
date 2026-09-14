"""기능 목록을 그룹 소제목과 함께 표시한다."""
from html import escape

def render_features(features) -> str:
    parts = []
    for group, label, unit in (("mvp", "MVP 기능", "개"), ("integration", "별도 연동", "건")):
        items = [f for f in features if f.group == group]
        if not items:
            continue
        parts.append(f"<p><strong>{label} {len(items)}{unit}</strong></p>")
        for f in items:
            parts.append(f"<p><strong>{escape(f.title)}</strong></p><p>{escape(f.description)}</p>")
    return "".join(parts)
