from django.db import migrations


def backfill_is_onboarded(apps, schema_editor):
    """
    is_onboarded 필드(0005) 도입 시 기존 유저 전원이 기본값 False로 깔렸다.
    프론트에서 온보딩(첫 로그인 강제 비밀번호 변경) 리다이렉트를 아직 이
    필드로 안 걸고 있어서 지금은 위험이 없지만, 나중에 그 로직을 연결하면
    기존 유저 전원이 갑자기 온보딩 화면에 갇히게 된다 — 그 전에 기존 유저는
    이미 온보딩이 끝난 것으로 표시해둔다(2026-09-08 결정, documents 화면
    작업 중 확인).
    """
    User = apps.get_model('users', 'User')
    User.objects.filter(is_onboarded=False).update(is_onboarded=True)


def reverse_noop(apps, schema_editor):
    # 되돌릴 때 굳이 다시 False로 깔 필요가 없다 — 원본 데이터를 복구하는 게
    # 아니라 단순 정책 반영이라 되돌림은 no-op으로 둔다.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_user_is_onboarded'),
    ]

    operations = [
        migrations.RunPython(backfill_is_onboarded, reverse_noop),
    ]
