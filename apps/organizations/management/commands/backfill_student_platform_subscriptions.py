"""Backfill per-student platform subscription rows for the current academic year."""

from django.core.management.base import BaseCommand

from apps.organizations.billing.student_subscription import backfill_student_platform_subscriptions


class Command(BaseCommand):
    help = "Create StudentPlatformSubscription rows for active students missing this year."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", dest="tenant_id", default=None)
        parser.add_argument("--paid-fraction", type=float, default=0.6)

    def handle(self, *args, **options):
        created = backfill_student_platform_subscriptions(
            tenant_id=options.get("tenant_id"),
            paid_fraction=options["paid_fraction"],
        )
        self.stdout.write(self.style.SUCCESS(f"Created {created} student platform subscription row(s)."))
