"""Reusable FilterSpec builders for report catalogs."""

from apps.core.exports.base import FilterSpec


def _choices_options(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


def invoice_status_filter(*, required: bool = False) -> FilterSpec:
    from apps.fees.enums import InvoiceStatus

    return FilterSpec(
        key="status",
        label="Status",
        type="select",
        required=required,
        options=_choices_options(InvoiceStatus.choices),
        group="criteria",
    )


def enquiry_status_filter(*, required: bool = False) -> FilterSpec:
    from apps.admissions.enums import EnquiryStatus

    return FilterSpec(
        key="status",
        label="Status",
        type="select",
        required=required,
        options=_choices_options(EnquiryStatus.choices),
        group="criteria",
    )


def leave_status_filter(*, required: bool = False) -> FilterSpec:
    from apps.hr.enums import LeaveStatus

    return FilterSpec(
        key="status",
        label="Leave status",
        type="select",
        required=required,
        options=_choices_options(LeaveStatus.choices),
        group="criteria",
    )
