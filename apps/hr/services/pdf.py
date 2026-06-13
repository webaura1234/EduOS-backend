"""Payslip PDF generation (bytes) + storage key (stubbed local key for Phase 1).

Real CloudFront-signed download lands in the Operations stage (F-301).
"""

from apps.fees.helpers.paise import paise_to_rupees_str


def generate_payslip_pdf(*, institution_name, employee_name, employee_code, period_label,
                         lines, gross_paise, deductions_paise, net_paise) -> bytes:
    """Minimal deterministic payslip document (plain-text bytes for Phase 1)."""
    out = [
        f"PAYSLIP — {institution_name}",
        f"Employee: {employee_name} ({employee_code})",
        f"Period: {period_label}",
        "-" * 40,
    ]
    for ln in lines:
        sign = "+" if ln["kind"] == "earning" else "-"
        out.append(f"{ln['name']:<24}{sign} {paise_to_rupees_str(ln['amountPaise'])}")
    out += [
        "-" * 40,
        f"Gross:      {paise_to_rupees_str(gross_paise)}",
        f"Deductions: {paise_to_rupees_str(deductions_paise)}",
        f"Net Pay:    {paise_to_rupees_str(net_paise)}",
    ]
    return ("\n".join(out)).encode("utf-8")


def store_payslip_pdf(*, branch_id, run_id, employee_id, pdf_bytes) -> str:
    """Stub storage: return a deterministic key (no real upload in Phase 1)."""
    return f"payslips/{branch_id}/{run_id}/{employee_id}.pdf"
