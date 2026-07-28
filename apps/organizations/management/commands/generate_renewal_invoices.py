"""
Generate renewal LicenseInvoice rows for subscription periods ending soon.

Billing amount = licenses_consumed × current net unit price.
Does not recreate StudentLicense rows (consume-forever).
"""

from django.core.management.base import BaseCommand

from apps.organizations.billing.license_allocator import run_renewal_invoice_pipeline


class Command(BaseCommand):
    help = "Generate renewal invoices for licensing periods ending within N days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--within-days",
            type=int,
            default=60,
            help="Issue renewals for periods ending within this many days (default 60).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count invoices that would be generated without writing.",
        )

    def handle(self, *args, **options):
        result = run_renewal_invoice_pipeline(
            within_days=options["within_days"],
            dry_run=options["dry_run"],
        )
        prefix = "Dry run — would generate" if options["dry_run"] else "Generated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {result['generated']} renewal invoice(s); "
                f"skipped {result['skipped']}; "
                f"ensured {result['ensuredPeriods']} following period(s)."
            )
        )
