from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("requirements", "0006_requirementdefinition_reject_reason")]
    operations = [
        migrations.AddField(model_name="requirementitem", name="related_feature", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="requirementitem", name="input_output", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="requirementitem", name="acceptance_criteria", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="requirementitem", name="note", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="requirementitem", name="source", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="requirementitem", name="review_status", field=models.TextField(blank=True, default="")),
    ]
