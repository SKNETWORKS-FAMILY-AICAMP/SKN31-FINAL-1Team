from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('requirements', '0008_requirementextractionjob'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='requirementdefinition', name='parent_definition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisions', to='requirements.requirementdefinition', verbose_name='이전 요구사항정의서 버전'),
        ),
        migrations.CreateModel(
            name='RequirementValidationReport',
            fields=[
                ('report_id', models.AutoField(primary_key=True, serialize=False)),
                ('scores', models.JSONField(default=dict)), ('summary', models.TextField(blank=True)),
                ('strengths', models.JSONField(default=list)), ('critical_issues', models.JSONField(default=list)),
                ('item_reviews', models.JSONField(default=list)), ('revised_items', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('requirement_definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='validation_reports', to='requirements.requirementdefinition')),
                ('applied_definition', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='applied_validation_report', to='requirements.requirementdefinition')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'requirement_validation_report', 'ordering': ['-created_at']},
        ),
    ]
