"""Gallery image model."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.gallery.enums import ProcessingStatus


class GalleryImage(BaseModel):
    """Single image within a gallery album."""

    album = models.ForeignKey(
        "gallery.GalleryAlbum",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image_key = models.CharField(max_length=512, blank=True, default="")
    thumbnail_key = models.CharField(max_length=512, blank=True, default="")
    staging_key = models.CharField(max_length=512, blank=True, default="")
    external_url = models.URLField(max_length=500, blank=True, default="")
    original_file_name = models.CharField(max_length=255, blank=True, default="")
    file_size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    processing_error = models.TextField(blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gallery_uploads",
    )

    class Meta:
        db_table = "gallery_image"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["album", "sort_order"]),
            models.Index(fields=["album", "content_hash"]),
        ]

    def __str__(self):
        return f"GalleryImage({self.original_file_name or self.pk})"
