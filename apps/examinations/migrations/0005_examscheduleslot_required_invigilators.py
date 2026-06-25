from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("examinations", "0004_internalmark"),
    ]

    operations = [
        migrations.AddField(
            model_name="examscheduleslot",
            name="required_invigilators",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Number of faculty required to invigilate this slot.",
                validators=[MinValueValidator(1)],
            ),
        ),
    ]
