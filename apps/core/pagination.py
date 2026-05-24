"""
Custom pagination classes for the EduOS platform.

Provides ``StandardPagination`` — the project-wide default referenced by
``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]``.
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Page-number pagination with sensible EduOS defaults.

    Configuration
    ~~~~~~~~~~~~~
    * **page_size** — ``20`` results per page by default.
    * **page_size_query_param** — clients can override by passing
      ``?page_size=50`` (up to ``max_page_size``).
    * **max_page_size** — hard cap at ``100`` to prevent abusive queries.

    Example request::

        GET /api/v1/students/?page=2&page_size=50
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
