# common/migrations/0002_add_task_status_approved.py
"""
2026-09-15: 프론트(projects/[id]/page.tsx, tasks/page.tsx, KanbanBoard.tsx)가
"승인됨(APPROVED)"을 "완료(COMPLETED)"와 별개의, 눈에 보이는 칸반/드롭다운 단계로
이미 설계해뒀다는 게 뒤늦게 확인됐다 — 그래서 TaskStatusCode.APPROVED를 DONE에
합치는 대신(한때 그렇게 했었음), TASK_STATUS 전용 code_id를 다시 시드해 별도
값으로 둔다. REJECTED->CANCELLED는 프론트에 같은 충돌이 없어(taskOverdue.ts가
DONE/CANCELLED/COMPLETED/REJECTED를 어차피 동일하게 취급) 그대로 둔다.
"""
from django.db import migrations


def add_task_approved_code(apps, schema_editor):
    """
    common_code 시드는 마이그레이션이 아니라 datadump.json(loaddata)으로 별도
    주입하는 관행이라(seed_demo.py 안내 문구 참고), 마이그레이션만으로 만들어진
    새 DB(예: manage.py test)엔 TASK_STATUS 그룹 자체가 없을 수 있다 — 그런
    환경에서 FK 위반으로 깨지지 않게 그룹이 있을 때만 넣는다. fixture로 시딩하는
    환경은 datadump.json에 이미 이 코드를 추가해뒀다(같은 커밋).
    """
    CommonCodeGroup = apps.get_model('common', 'CommonCodeGroup')
    if not CommonCodeGroup.objects.filter(pk='TASK_STATUS').exists():
        return
    CommonCode = apps.get_model('common', 'CommonCode')
    CommonCode.objects.get_or_create(
        code_id='TASK_APPROVED',
        defaults={'group_id': 'TASK_STATUS', 'code_name': '승인됨', 'sort_order': 0},
    )


def remove_task_approved_code(apps, schema_editor):
    CommonCode = apps.get_model('common', 'CommonCode')
    CommonCode.objects.filter(code_id='TASK_APPROVED').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_task_approved_code, remove_task_approved_code),
    ]
