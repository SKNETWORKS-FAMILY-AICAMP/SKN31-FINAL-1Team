from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def carry_owner_setting(apps, schema_editor):
    Watch = apps.get_model('meetings', 'MeetingWatchSetting')
    for control in Watch.objects.exclude(requested_by_id=None):
        control.user_id = control.requested_by_id
        control.save(update_fields=['user'])
    Watch.objects.filter(user_id=None).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0015_meetingwatchsetting'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField('meetingwatchsetting', 'folder', models.CharField(blank=True, default='', max_length=1000)),
        migrations.AddField('meetingwatchsetting', 'user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meeting_watch', to=settings.AUTH_USER_MODEL)),
        migrations.RunPython(carry_owner_setting, migrations.RunPython.noop),
        migrations.RemoveField('meetingwatchsetting', 'requested_by'),
        migrations.AlterField('meetingwatchsetting', 'user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='meeting_watch', to=settings.AUTH_USER_MODEL)),
        migrations.AlterField('meetingwatchsetting', 'id', models.AutoField(primary_key=True, serialize=False)),
    ]
