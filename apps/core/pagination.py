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


def paginate_queryset(request, queryset, serialize_row, *, pagination_class=StandardPagination) -> dict:
    """
    Paginate a queryset (or plain list) inside a manual ``APIView`` and return the
    standard ``{count, next, previous, results}`` envelope as a plain dict.

    Unlike ``ListAPIView``/``ModelViewSet``, a hand-written ``APIView`` that builds a
    compound response (e.g. several lists in one payload) doesn't get DRF's automatic
    pagination for free. This helper closes that gap without requiring every such view
    to be rewritten as a `ListAPIView` — call it once per list inside the view's `get()`.

    The queryset is sliced *before* `serialize_row` runs, so only the current page's
    rows are ever serialized — this is what keeps the per-request cost bounded
    regardless of how large the underlying table is.

    Example::

        def get(self, request):
            qs = list_managed_users(tenant_id, branch_id=branch_id)
            return Response({
                "users": paginate_queryset(request, qs, managed_user_dict),
                ...
            })
    """
    paginator = pagination_class()
    page = paginator.paginate_queryset(queryset, request)
    results = [serialize_row(obj) for obj in page]
    response = paginator.get_paginated_response(results)
    return response.data
