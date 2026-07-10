# Generated migration for StudentConcession rename and status values.

from django.db import migrations, models


def migrate_concession_statuses(apps, schema_editor):
    StudentConcession = apps.get_model("fees", "StudentConcession")
    mapping = {
        "approved": "active",
        "pending": "revoked",
        "rejected": "revoked",
    }
    for old, new in mapping.items():
        StudentConcession.objects.filter(status=old).update(status=new)


class Migration(migrations.Migration):

    dependencies = [
        ("fees", "0003_fee_head_and_structure_status"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ConcessionRequest",
            new_name="StudentConcession",
        ),
        migrations.AlterModelOptions(
            name="studentconcession",
            options={
                "verbose_name": "Student Concession",
                "verbose_name_plural": "Student Concessions",
            },
        ),
        migrations.AlterField(
            model_name="studentconcession",
            name="branch",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="student_concessions",
                to="organizations.branch",
            ),
        ),
        migrations.AlterField(
            model_name="studentconcession",
            name="rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="student_concessions",
                to="fees.concessionrule",
            ),
        ),
        migrations.AlterField(
            model_name="studentconcession",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("revoked", "Revoked"),
                    ("expired", "Expired"),
                ],
                default="active",
                max_length=10,
            ),
        ),
        migrations.RunPython(migrate_concession_statuses, migrations.RunPython.noop),
    ]
