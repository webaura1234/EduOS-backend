"""Two-plan pricing migration: standard/ai tiers + per-student AI credit ledger."""

from django.db import migrations, models
import django.db.models.deletion
import uuid


LEGACY_TO_CURRENT = {
    "starter": "standard",
    "growth": "standard",
    "enterprise": "ai",
}


def migrate_plan_slugs(apps, schema_editor):
    PlanSubscription = apps.get_model("organizations", "PlanSubscription")
    StudentPlatformSubscription = apps.get_model("organizations", "StudentPlatformSubscription")
    PlatformPlanDefinition = apps.get_model("organizations", "PlatformPlanDefinition")

    for old, new in LEGACY_TO_CURRENT.items():
        PlanSubscription.objects.filter(plan=old).update(plan=new)
        StudentPlatformSubscription.objects.filter(plan=old).update(plan=new)

    PlatformPlanDefinition.objects.filter(plan__in=LEGACY_TO_CURRENT).delete()

    PlatformPlanDefinition.objects.update_or_create(
        plan="standard",
        defaults={
            "label": "Standard ERP",
            "max_branches": 0,
            "max_students": 0,
            "included_features": [],
            "description": "Full core ERP for every school — all modules, no caps.",
            "price_per_student_inr": 299,
            "included_ai_credits_per_student": 0,
            "includes_ai": False,
        },
    )
    PlatformPlanDefinition.objects.update_or_create(
        plan="ai",
        defaults={
            "label": "AI ERP",
            "max_branches": 0,
            "max_students": 0,
            "included_features": [],
            "description": "Standard ERP plus AI capabilities with per-student credits.",
            "price_per_student_inr": 499,
            "included_ai_credits_per_student": 50,
            "includes_ai": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0013_license_payment_branch"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformplandefinition",
            name="price_per_student_inr",
            field=models.PositiveIntegerField(default=299),
        ),
        migrations.AddField(
            model_name="platformplandefinition",
            name="included_ai_credits_per_student",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="platformplandefinition",
            name="includes_ai",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="platformplandefinition",
            name="max_branches",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="0 = unlimited (core ERP is not branch-gated).",
            ),
        ),
        migrations.AlterField(
            model_name="platformplandefinition",
            name="max_students",
            field=models.PositiveIntegerField(
                default=0,
                help_text="0 = unlimited (core ERP is not student-gated).",
            ),
        ),
        migrations.AlterField(
            model_name="plansubscription",
            name="plan",
            field=models.CharField(
                choices=[("standard", "Standard ERP"), ("ai", "AI ERP")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="studentplatformsubscription",
            name="plan",
            field=models.CharField(
                choices=[("standard", "Standard ERP"), ("ai", "AI ERP")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="StudentAiCreditBalance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("balance", models.PositiveIntegerField(default=0)),
                (
                    "student_user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_credit_balance",
                        to="accounts.user",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_ai_credit_balances",
                        to="organizations.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student AI credit balance",
                "verbose_name_plural": "Student AI credit balances",
                "db_table": "organizations_student_ai_credit_balance",
            },
        ),
        migrations.CreateModel(
            name="StudentAiCreditTxn",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("txn_type", models.CharField(
                    choices=[
                        ("grant", "Grant"),
                        ("consume", "Consume"),
                        ("recharge", "Recharge"),
                        ("admin_adjust", "Admin adjust"),
                        ("period_reset", "Period reset"),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ("amount", models.IntegerField(help_text="Positive for grants/recharges; negative for consumption.")),
                ("balance_after", models.PositiveIntegerField()),
                ("idempotency_key", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.user",
                    ),
                ),
                (
                    "student_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_credit_txns",
                        to="accounts.user",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_ai_credit_txns",
                        to="organizations.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Student AI credit transaction",
                "verbose_name_plural": "Student AI credit transactions",
                "db_table": "organizations_student_ai_credit_txn",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="studentaicreditbalance",
            index=models.Index(fields=["tenant"], name="organizatio_tenant__a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="studentaicredittxn",
            index=models.Index(fields=["tenant", "student_user", "-created_at"], name="organizatio_tenant__d4e5f6_idx"),
        ),
        migrations.AddConstraint(
            model_name="studentaicredittxn",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("student_user", "idempotency_key"),
                name="unique_ai_credit_idempotency_per_student",
            ),
        ),
        migrations.RunPython(migrate_plan_slugs, migrations.RunPython.noop),
    ]
