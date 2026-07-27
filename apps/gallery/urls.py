"""Gallery URL routes."""

from django.urls import path

from apps.gallery.views.api import (
    AdminAlbumCoverView,
    AdminAlbumDetailView,
    AdminAlbumListCreateView,
    AdminAlbumReorderView,
    AdminImageBulkDeleteView,
    AdminImageConfirmView,
    AdminImageMoveView,
    AdminImageStagingUploadView,
    AdminImagePresignView,
    AdminImageStatusView,
    AdminStorageUsageView,
    FacultyImageConfirmView,
    FacultyImagePresignView,
    GalleryAlbumCoverFileView,
    GalleryImageFileView,
    GalleryMediaView,
    ReaderAlbumDetailView,
    ReaderAlbumListView,
)

app_name = "gallery"

urlpatterns = [
    path("media/", GalleryMediaView.as_view(), name="gallery-media"),
    path("storage/", AdminStorageUsageView.as_view(), name="storage-usage"),
    path("albums/", AdminAlbumListCreateView.as_view(), name="albums"),
    path("albums/me/", ReaderAlbumListView.as_view(), name="reader-albums"),
    path("albums/me/<uuid:album_id>/", ReaderAlbumDetailView.as_view(), name="reader-album-detail"),
    path("albums/<uuid:album_id>/", AdminAlbumDetailView.as_view(), name="album-detail"),
    path("albums/<uuid:album_id>/reorder-images/", AdminAlbumReorderView.as_view(), name="album-reorder"),
    path("albums/<uuid:album_id>/set-cover/", AdminAlbumCoverView.as_view(), name="album-cover"),
    path("albums/<uuid:album_id>/cover-file/", GalleryAlbumCoverFileView.as_view(), name="album-cover-file"),
    path("images/presign/", AdminImagePresignView.as_view(), name="images-presign"),
    path("images/<uuid:image_id>/staging/", AdminImageStagingUploadView.as_view(), name="image-staging-upload"),
    path("images/<uuid:image_id>/file/", GalleryImageFileView.as_view(), name="image-file"),
    path("images/presign/faculty/", FacultyImagePresignView.as_view(), name="faculty-images-presign"),
    path("images/confirm/", AdminImageConfirmView.as_view(), name="images-confirm"),
    path("images/confirm/faculty/", FacultyImageConfirmView.as_view(), name="faculty-images-confirm"),
    path("images/bulk-delete/", AdminImageBulkDeleteView.as_view(), name="images-bulk-delete"),
    path("images/move/", AdminImageMoveView.as_view(), name="images-move"),
    path("images/<uuid:image_id>/status/", AdminImageStatusView.as_view(), name="image-status"),
]
