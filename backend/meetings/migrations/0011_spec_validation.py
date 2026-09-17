from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('meetings', '0010_meetinganalysisjob'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='specdocument', name='version', field=models.PositiveIntegerField(default=1, verbose_name='기획서 버전')),
        migrations.AddField(model_name='specdocument', name='parent_spec', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisions', to='meetings.specdocument', verbose_name='이전 기획서 버전')),
        migrations.CreateModel(
            name='SpecValidationReport',
            fields=[
                ('report_id', models.AutoField(primary_key=True, serialize=False)),
                ('scores', models.JSONField(default=dict)), ('summary', models.TextField(blank=True)),
                ('strengths', models.JSONField(default=list)), ('critical_issues', models.JSONField(default=list)),
                ('section_reviews', models.JSONField(default=list)), ('revised_document', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('applied_spec', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='applied_validation_report', to='meetings.specdocument')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('spec', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='validation_reports', to='meetings.specdocument')),
            ],
            options={'db_table': 'spec_validation_report', 'ordering': ['-created_at']},
        ),
    ]
