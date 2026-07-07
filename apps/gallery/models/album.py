"""Gallery album model."""

from django.db import models

from apps.core.models import BaseModel
from apps.core.models.mixins import BranchScopedMixin
from apps.gallery.enums import AlbumVisibility


class GalleryAlbum(BaseModel, BranchScopedMixin):
    """Branch-scoped photo album — school-wide (batch=NULL) or class-specific."""

    batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="gallery_albums",
        help_text="NULL = school album; set = class album.",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="gallery_albums",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120)
    description = models.TextField(blank=True, default="")
    cover_image_key = models.CharField(max_length=512, blank=True, default="")
    total_images = models.PositiveIntegerField(default=0)
    visibility = models.CharField(
        max_length=20,
        choices=AlbumVisibility.choices,
        default=AlbumVisibility.STUDENTS,
    )
    event_tag = models.CharField(max_length=100, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "gallery_album"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["branch", "batch", "slug"]),
            models.Index(fields=["branch", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "batch", "slug"],
                name="unique_gallery_album_slug_per_scope",
            ),
        ]

    def __str__(self):
        scope = self.batch.name if self.batch_id else "school"
        return f"GalleryAlbum({self.title} / {scope})"

    @property
    def is_school_album(self) -> bool:
        return self.batch_id is None
