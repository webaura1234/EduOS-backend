"""
Move licensing subscription periods past their end date into grace, and past
their grace window into expired. Intended for a daily cron/scheduler run;
the Platform Owner trial pipeline action also triggers it.
"""

from django.core.management.base import BaseCommand

from apps.organizations.billing.license_allocator import run_expiry_pipeline


class Command(BaseCommand):
    help = "Run the licensing subscription grace/expiry pipeline."

    def handle(self, *args, **options):
        result = run_expiry_pipeline()
        self.stdout.write(
            self.style.SUCCESS(
                f"License expiry pipeline: {result['movedToGrace']} moved to grace, "
                f"{result['expired']} expired."
            )
        )
