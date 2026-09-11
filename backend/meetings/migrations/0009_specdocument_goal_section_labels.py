from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("meetings", "0008_specdocument_goals_alter_specdocument_key_features_and_more")]
    operations = [
        migrations.AlterField(model_name="specdocument", name="problem_definition", field=models.TextField(null=True, blank=True, verbose_name="2. 핵심 목표")),
        migrations.AlterField(model_name="specdocument", name="goals", field=models.TextField(null=True, blank=True, verbose_name="3. 세부 목표 및 문제 정의")),
    ]
