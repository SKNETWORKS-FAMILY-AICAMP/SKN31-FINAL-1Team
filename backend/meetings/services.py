#meetings/services.py
import json
import re
import html

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.db.models import Max

from meetings.models import MeetingNote, SpecDocument, SpecValidationReport
from meetings.serializers import MeetingNoteSerializer, SpecDocumentSerializer
from projects.models import PipelineHistory
from common.models import CommonCode

from meeting_analysis.node import run as analyze_meeting
from plan_draft.agent import run as generate_plan
from plan_review.agent import run as review_plan

User = get_user_model()

# ai/plan_draft/schemas.py의 SECTION_SPEC(노드②의 설계도)과 동일한 key ↔
# SpecDocument 필드명 매핑. 근거자료(evidence_data)도 이 키로 저장해야 프론트
# (documents/page.tsx의 EVIDENCE_KEY_ALIASES)가 올바른 섹션에 붙여준다.
SECTION_KEY_TO_FIELD = {
    'overview': 'overview',
    'problem': 'problem_definition',
    'users': 'target_users',
    'features': 'key_features',
    'goals': 'goals',
    'tech_scope': 'tech_stack',
    'decisions': 'final_decisions',
}

NOT_DISCUSSED = "회의에서 논의되지 않았습니다."


def _strip_html_tags(text):
    if not text:
        return ""
    text_str = str(text)
    decoded_text = html.unescape(text_str)
    clean_text = re.sub(r'<[^>]+>', ' ', decoded_text)
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)
    clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
    return clean_text.strip()


def run_meeting_analysis(note_id: int, actor_user_id, on_stage=None) -> dict:
    """
    "기획서 생성" 버튼 — 회의록 AI 분석(노드①) → 기획서 초안 생성(노드②)을 순서대로
    호출해 SpecDocument를 upsert한다. MeetingNoteAnalyzeView.post에 있던 로직을
    그대로 옮긴 것(2026-09-15, 백그라운드 실행 + 진행 단계 폴링 도입) — 로직/순서는
    바꾸지 않았다.

    on_stage: 있으면 각 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택). 노드①이
    실측 ~100초로 특히 오래 걸려(2026-09-14 "느리다" 문의 확인) 업무 배분 실행과
    같은 방식으로 체감을 개선한다.
    """
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    meeting = MeetingNote.objects.get(pk=note_id)
    actor = User.objects.filter(pk=actor_user_id).first() if actor_user_id else None

    meeting.status = MeetingNote.Status.PROCESSING
    meeting.save()

    try:
        # 2026-09-15: 두 노드 다 내부적으로 몇 단계씩 더 있어(구조화→근거검증→
        # 정합성검사, 초안작성→목록조립→병합), 여기서 뭉뚱그려 부르지 않고
        # on_stage를 그대로 넘겨 노드 내부에서 세분화된 라벨을 직접 보고하게 한다.
        analysis_result = analyze_meeting(meeting.content, str(meeting.pk), on_stage=on_stage)
        structured_data = analysis_result.data if hasattr(analysis_result, 'data') else analysis_result

        proposal_id = f"PLN-{meeting.pk:03d}"
        doc = generate_plan(structured_data, proposal_id, on_stage=on_stage)

        if hasattr(doc, 'model_dump'):
            plan_dict = doc.model_dump(mode="json")
        elif hasattr(doc, 'dict'):
            plan_dict = doc.dict()
        elif isinstance(doc, dict):
            plan_dict = doc
        else:
            plan_dict = {}

        summary_val = structured_data.get('summary') if isinstance(structured_data, dict) else None
        meeting.summary_content = summary_val or f"[{meeting.title}] AI 분석이 완료되었습니다."
        meeting.status = MeetingNote.Status.REVIEWED
        meeting.save()

        sections_map = {}
        evidence_map = {}
        for sec in (plan_dict.get('sections') or []):
            if not isinstance(sec, dict):
                continue
            sec_key = sec.get('key')
            if not sec_key or not isinstance(sec_key, str):
                continue

            content = sec.get('content_html') or ""
            if not content and isinstance(sec.get('items'), list):
                content = "\n".join(f"- {item}" for item in sec['items'] if isinstance(item, (str, int)))
            if not content and isinstance(sec.get('features'), list):
                lines = []
                for f in sec['features']:
                    if isinstance(f, dict):
                        lines.append(f"• {f.get('title', '')}: {f.get('description', '')}")
                content = "\n".join(lines)

            sections_map[sec_key] = content

            quotes = [
                e.get('quote') for e in (sec.get('evidence') or [])
                if isinstance(e, dict) and e.get('status') == 'verified' and e.get('quote')
            ]
            field_name = SECTION_KEY_TO_FIELD.get(sec_key)
            if quotes and field_name:
                evidence_map[field_name] = "\n".join(f"- {q}" for q in quotes)

        def section_or_not_discussed(key):
            val = sections_map.get(key, "")
            return val if val.strip() else NOT_DISCUSSED

        spec_defaults = {
            'title': f"{meeting.title} - 기획 초안",
            'overview': section_or_not_discussed('overview'),
            'problem_definition': section_or_not_discussed('problem'),
            'target_users': section_or_not_discussed('users'),
            'key_features': section_or_not_discussed('features'),
            'goals': section_or_not_discussed('goals'),
            'tech_stack': section_or_not_discussed('tech_scope'),
            'final_decisions': section_or_not_discussed('decisions'),
        }
        if evidence_map:
            spec_defaults['evidence_data'] = json.dumps(evidence_map, ensure_ascii=False)

        period_match = re.search(
            r'(\d{4}-\d{2}-\d{2})\s*(?:~|-|부터)\s*(\d{4}-\d{2}-\d{2})',
            meeting.content or "",
        )
        if period_match:
            spec_defaults['period_start'] = period_match.group(1)
            spec_defaults['period_end'] = period_match.group(2)

        # 검증 보완 적용으로 여러 버전이 존재할 수 있으므로 최신 버전만 갱신한다.
        spec = SpecDocument.objects.filter(meeting=meeting).order_by('-version', '-created_at').first()
        if spec is None:
            spec = SpecDocument.objects.create(meeting=meeting, **spec_defaults)
        else:
            for field, value in spec_defaults.items():
                setattr(spec, field, value)
            spec.save()

        if meeting.project_id:
            PipelineHistory.objects.create(
                project=meeting.project,
                meeting=meeting,
                spec=spec,
                step_type='SPEC_AI_GENERATED',
                title=f"기획서 생성: {spec.title}",
                description=f"실행자: {actor.username if actor else '알 수 없음'} 사원",
                actor=actor,
            )

        return {
            "status": "success",
            "message": "회의록 AI 분석 및 기획서 초안 생성이 완료되었습니다.",
            "meeting": MeetingNoteSerializer(meeting).data,
            "created_spec": SpecDocumentSerializer(spec).data,
        }

    except Exception as e:
        meeting.status = MeetingNote.Status.DRAFT
        meeting.save()
        return {
            "status": "error",
            "message": "AI 기획서 생성 중 오류가 발생했습니다.",
            "detail": str(e),
        }


PLAN_FIELDS = tuple(SECTION_KEY_TO_FIELD.values())


def _normalize_plan_html(value: str) -> str:
    """검증 노드의 일반 텍스트 응답을 기존 기획서의 제한 HTML 형식으로 맞춘다.

    기존 생성 노드는 <p>/<ul>/<li>/<strong>을 반환하지만 검증 모델은 때때로
    ``1) ... 2) ...``를 한 줄로 반환한다. 그대로 저장하면 브라우저에서 한 문단으로
    붙으므로 번호/불릿을 목록으로 변환한다. 일반 텍스트는 escape해 HTML 삽입도 막는다.
    """
    raw = str(value or '').strip()
    if not raw:
        return ''
    if re.search(r'<\s*(?:p|ul|li|strong)\b', raw, flags=re.IGNORECASE):
        # 화면에서도 DOMPurify로 한 번 더 제한하지만 저장 데이터 역시 허용 태그만 남긴다.
        clean = re.sub(r'</?(?!p\b|ul\b|li\b|strong\b)[a-zA-Z][^>]*>', '', raw)
        return clean.strip()

    # 한 줄 안에 이어진 "1) ... 2) ..." 항목도 각 줄로 분리한다.
    raw = re.sub(r'\s+(?=(?:\d+\)|[-•])\s+)', '\n', raw)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    blocks = []
    list_items = []

    def flush_list():
        if list_items:
            blocks.append('<ul>' + ''.join(f'<li>{html.escape(item)}</li>' for item in list_items) + '</ul>')
            list_items.clear()

    for line in lines:
        match = re.match(r'^(?:\d+\)|[-•])\s*(.+)$', line)
        if match:
            list_items.append(match.group(1).strip())
        else:
            flush_list()
            blocks.append(f'<p>{html.escape(line)}</p>')
    flush_list()
    return ''.join(blocks)


def validate_spec_document(spec: SpecDocument, actor) -> SpecValidationReport:
    document = {field: getattr(spec, field) or "" for field in PLAN_FIELDS}
    result = review_plan(spec.meeting.content or "", document)
    data = result.model_dump(mode='json')
    return SpecValidationReport.objects.create(
        spec=spec, scores=data['scores'], summary=data['summary'],
        strengths=data['strengths'], critical_issues=data['critical_issues'],
        section_reviews=data['section_reviews'], revised_document=data['revised_document'],
        created_by=actor,
    )


@transaction.atomic
def apply_spec_validation(report: SpecValidationReport) -> SpecDocument:
    """검토 당시 원본은 보존하고 보완된 새 버전을 만든다. 중복 적용은 멱등적이다."""
    report = SpecValidationReport.objects.select_for_update().select_related('spec', 'applied_spec').get(pk=report.pk)
    if report.applied_spec_id:
        return report.applied_spec
    source = report.spec
    next_version = (SpecDocument.objects.filter(meeting=source.meeting).aggregate(v=Max('version'))['v'] or 0) + 1
    values = {
        field: _normalize_plan_html((report.revised_document or {}).get(field, getattr(source, field)))
        for field in PLAN_FIELDS
    }
    for field in ('period_start', 'period_end', 'background', 'target_scope'):
        values[field] = getattr(source, field)
    report_evidence = {}
    for section in report.section_reviews or []:
        field = section.get('section_key')
        evidence = section.get('evidence') or []
        if field in PLAN_FIELDS and evidence:
            report_evidence[field] = "\n".join(f"- {quote}" for quote in evidence)
    values['evidence_data'] = json.dumps(report_evidence, ensure_ascii=False) if report_evidence else None
    values.update(
        title=f"{source.title.rsplit(' (v', 1)[0]} (v{next_version})",
        version=next_version,
        parent_spec=source,
        status_code=CommonCode.objects.filter(
            group_id='PROPOSAL_STATUS', code_id='PROPOSAL_DRAFT'
        ).first(),
    )
    revised = SpecDocument.objects.create(meeting=source.meeting, **values)
    report.applied_spec = revised
    report.applied_at = timezone.now()
    report.save(update_fields=['applied_spec', 'applied_at'])
    return revised
