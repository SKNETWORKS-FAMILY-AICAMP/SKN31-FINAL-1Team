from django.db import migrations


#  code_id는 CommonCode 테이블 전체에서 전역 유일한 PK라(그룹별로 스코프되지 않음),
#  REQSPEC_STATUS가 이미 DRAFT/PENDING_REVIEW/APPROVED/REJECTED를 선점하고 있어서 그대로
#  못 쓴다(실제로 시도해보니 UNIQUE constraint 위반) — PROPOSAL_ 접두사로 구분한다.
CODES = [
    ("PROPOSAL_DRAFT", "초안", 0),
    ("PROPOSAL_PENDING_REVIEW", "검토대기", 1),
    ("PROPOSAL_APPROVED", "승인완료", 2),
    ("PROPOSAL_REJECTED", "반려", 3),
]


def seed_proposal_status(apps, schema_editor):
    # PROPOSAL_STATUS 그룹 행 자체는 이미 있었지만(DB_front_back.xlsx 시드 데이터) 소속 코드가
    # 비어 있어서 기획서 승인/반려 워크플로우가 상태값을 못 찾는 상태였다 — REQSPEC_STATUS와
    # 동일한 4단계로 채운다.
    CommonCodeGroup = apps.get_model('common', 'CommonCodeGroup')
    CommonCode = apps.get_model('common', 'CommonCode')
    group, _ = CommonCodeGroup.objects.get_or_create(
        group_code='PROPOSAL_STATUS',
        defaults={'group_name': 'PROPOSAL - STATUS', 'is_active': True},
    )
    for code_id, code_name, sort_order in CODES:
        CommonCode.objects.get_or_create(
            code_id=code_id,
            defaults={'group': group, 'code_name': code_name, 'sort_order': sort_order, 'is_active': True},
        )


def unseed_proposal_status(apps, schema_editor):
    CommonCode = apps.get_model('common', 'CommonCode')
    CommonCode.objects.filter(code_id__in=[c[0] for c in CODES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0004_meetingnote_project'),
        ('common', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_proposal_status, unseed_proposal_status),
    ]
