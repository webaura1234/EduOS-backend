"""Backfill gallery stored_bytes and tenant STORAGE_BYTES quotas."""

from django.core.management.base import BaseCommand
from django.db.models import F

from apps.gallery.enums import ProcessingStatus
from apps.gallery.models import GalleryImage
from apps.organizations.billing.storage_quota import recompute_gallery_usage, sync_storage_limit_for_tenant
from apps.organizations.models import Tenant


class Command(BaseCommand):
    help = "Sync storage_limit_gb from licenses and recompute STORAGE_BYTES from gallery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=str,
            default=None,
            help="Limit to one tenant UUID.",
        )

    def handle(self, *args, **options):
        # Legacy ready rows without stored_bytes: approximate with original file_size.
        updated = (
            GalleryImage.objects.filter(
                processing_status=ProcessingStatus.READY,
                stored_bytes=0,
                file_size__gt=0,
                is_active=True,
            ).update(stored_bytes=F("file_size"))
        )
        self.stdout.write(f"Approximated stored_bytes on {updated} legacy image(s).")

        qs = Tenant.objects.filter(is_active=True)
        tenant_id = options.get("tenant_id")
        if tenant_id:
            qs = qs.filter(pk=tenant_id)

        count = 0
        for tenant in qs.iterator():
            sync_storage_limit_for_tenant(tenant)
            usage = recompute_gallery_usage(tenant)
            self.stdout.write(f"{tenant.subdomain}: limit synced, usage={usage} bytes")
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Done. {count} tenant(s)."))
