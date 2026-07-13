# Generated merge — reconciles concurrent 0019 branches:
#   0019_sequential_id_counter  (StudentIDCounter → SequentialIdCounter)
#   0019_user_avatar_s3_key     (User.avatar → avatar_s3_key)
#
# No overlapping schema changes; operations are independent.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_sequential_id_counter"),
        ("accounts", "0019_user_avatar_s3_key"),
    ]

    operations = []
