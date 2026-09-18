import re

from django.db import transaction
from django.utils import timezone

from common.models import CommonCode
from requirements.models import (
    RequirementDefinition, RequirementItem, RequirementValidationReport,
)
from requirement_review.agent import run as review_requirements


ITEM_FIELDS = (
    'req_code', 'req_name', 'description', 'related_feature', 'input_output',
    'acceptance_criteria', 'note', 'source', 'review_status', 'difficulty',
    'category', 'category_2',
)


def _plan_payload(spec):
    fields = ('title', 'overview', 'problem_definition', 'goals', 'target_users',
              'key_features', 'tech_stack', 'final_decisions')
    return {field: getattr(spec, field, None) or '' for field in fields}


def _item_payload(item):
    data = {field: getattr(item, field, '') or '' for field in ITEM_FIELDS}
    data['priority'] = item.priority_code_id or 'MEDIUM'
    return data


def validate_requirement_definition(req_def, actor):
    result = review_requirements(
        _plan_payload(req_def.spec),
        [_item_payload(item) for item in req_def.items.all()],
    ).model_dump(mode='json')
    return RequirementValidationReport.objects.create(
        requirement_definition=req_def,
        scores=result['scores'], summary=result['summary'], strengths=result['strengths'],
        critical_issues=result['critical_issues'], item_reviews=result['item_reviews'],
        revised_items=result['revised_items'], created_by=actor,
    )


def _next_version(value):
    match = re.search(r'(\d+)(?:\.(\d+))?', value or '')
    major = int(match.group(1)) if match else 1
    return f'v{major + 1}.0'


@transaction.atomic
def apply_requirement_validation(report):
    report = RequirementValidationReport.objects.select_for_update().select_related(
        'requirement_definition__spec', 'applied_definition'
    ).get(pk=report.pk)
    if report.applied_definition_id:
        return report.applied_definition

    source = report.requirement_definition
    draft = CommonCode.objects.filter(group_id='REQSPEC_STATUS', code_id='DRAFT').first()
    revised = RequirementDefinition.objects.create(
        spec=source.spec, project=source.project, title=source.title,
        version=_next_version(source.version), description=source.description,
        status_code=draft, created_by=source.created_by, parent_definition=source,
    )
    priorities = {code.code_id: code for code in CommonCode.objects.filter(group_id='REQ_PRIORITY')}
    items = []
    for index, raw in enumerate(report.revised_items or [], start=1):
        priority = str(raw.get('priority') or 'MEDIUM').upper()
        priority_obj = priorities.get(priority) or priorities.get(f'PRIORITY_{priority}') or priorities.get(f'REQ_PRIORITY_{priority}')
        items.append(RequirementItem(
            req_def=revised, order=index, priority_code=priority_obj,
            **{field: raw.get(field, '') for field in ITEM_FIELDS},
        ))
    if not items:
        raise ValueError('AI 보완 결과에 요구사항 항목이 없습니다.')
    RequirementItem.objects.bulk_create(items)
    report.applied_definition = revised
    report.applied_at = timezone.now()
    report.save(update_fields=['applied_definition', 'applied_at'])
    return revised
