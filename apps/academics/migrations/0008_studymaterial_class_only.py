# Study materials are class/batch-scoped only (session-wise fields removed).

from django.db import migrations, models
import django.db.models.deletion


def delete_legacy_session_materials(apps, schema_editor):
    StudyMaterial = apps.get_model("academics", "StudyMaterial")
    StudyMaterial.objects.filter(batch_id__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0007_remove_studymaterial_academics_s_branch__5e550b_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(delete_legacy_session_materials, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="studymaterial",
            name="session_date",
        ),
        migrations.RemoveField(
            model_name="studymaterial",
            name="timetable_entry",
        ),
        migrations.AlterField(
            model_name="studymaterial",
            name="batch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_materials",
                to="academics.batch",
            ),
        ),
    ]
