"""CSV rendering for report exports — shared by inline runner and Celery tasks."""

import csv
import io

from apps.core.exports.base import Column


def rows_to_csv_bytes(rows: list[dict], columns: list[Column] | None = None) -> bytes:
    """Serialize row dicts to UTF-8 CSV with BOM (Excel-friendly)."""
    if not rows:
        if columns:
            buf = io.StringIO()
            csv.writer(buf).writerow([c.label for c in columns])
            return buf.getvalue().encode("utf-8-sig")
        return b""

    if columns:
        fieldnames = [c.key for c in columns]
        header_labels = [c.label for c in columns]
    else:
        fieldnames = sorted({k for r in rows for k in r.keys()})
        header_labels = fieldnames

    buf = io.StringIO()
    csv.writer(buf).writerow(header_labels)
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def queryset_to_csv_bytes(definition, qs, params: dict) -> tuple[bytes, list[dict]]:
    """Stream a queryset export to CSV bytes; returns (csv_bytes, row_dicts)."""
    columns = definition.get_columns(params)
    buf = io.StringIO()
    csv.writer(buf).writerow([c.label for c in columns])
    writer = csv.DictWriter(buf, fieldnames=[c.key for c in columns], extrasaction="ignore")
    rows_dicts = []
    for obj in qs.iterator(chunk_size=500):
        row = definition.get_row(obj)
        rows_dicts.append(row)
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig"), rows_dicts
