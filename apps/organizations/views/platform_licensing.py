"""Platform-owner licensing APIs — overview, tenant detail, payments, invoices,
and subscription-period extension.

All mutations write a PlatformAuditLog entry (category="licensing").
"""

import datetime

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOwner
from apps.organizations.billing import license_allocator as alloc
from apps.organizations.enums import LicenseInvoiceType, LicensePaymentMode
from apps.organizations.models import LicenseInvoice, Tenant, TenantSubscriptionPeriod
from apps.organizations.queries import licensing as q
from apps.organizations.queries.platform_ops import log_audit
from apps.organizations.serializers.licensing import invoice_dict, payment_dict, period_dict


def _get_tenant(tenant_id) -> Tenant | None:
    return Tenant.objects.filter(pk=tenant_id, is_active=True).first()


def _parse_date(value) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


class PlatformLicensingOverviewView(APIView):
    """GET /api/v1/organizations/platform/licensing/overview/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(q.platform_overview())


class PlatformLicensingTenantDetailView(APIView):
    """GET /api/v1/organizations/platform/licensing/tenants/<tenant_id>/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request, tenant_id) -> Response:
        tenant = _get_tenant(tenant_id)
        if tenant is None:
            return Response({"error": "School not found."}, status=http.HTTP_404_NOT_FOUND)
        branch_id = request.query_params.get("branchId") or None
        detail = q.tenant_detail(tenant, branch_id=branch_id)
        detail["periods"] = q.periods_for_tenant(tenant)
        return Response(detail)


class PlatformLicensingPaymentsView(APIView):
    """GET+POST /api/v1/organizations/platform/licensing/payments/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response({"payments": q.payment_history(request.query_params.get("tenantId"))})

    def post(self, request) -> Response:
        data = request.data
        tenant = _get_tenant(data.get("tenantId"))
        if tenant is None:
            return Response({"error": "School not found."}, status=http.HTTP_404_NOT_FOUND)

        try:
            licenses_granted = int(data.get("licensesGranted", 0))
            amount_inr = int(data.get("amountInr", 0))
        except (TypeError, ValueError):
            return Response(
                {"error": "licensesGranted and amountInr must be numbers."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if licenses_granted <= 0:
            return Response(
                {"error": "licensesGranted must be at least 1."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if amount_inr < 0:
            return Response({"error": "amountInr cannot be negative."}, status=http.HTTP_400_BAD_REQUEST)

        payment_mode = data.get("paymentMode", LicensePaymentMode.CASH)
        if payment_mode not in LicensePaymentMode.values:
            return Response({"error": "Invalid paymentMode."}, status=http.HTTP_400_BAD_REQUEST)

        invoice = None
        if data.get("invoiceId"):
            invoice = LicenseInvoice.objects.filter(pk=data["invoiceId"], tenant=tenant).first()

        try:
            payment = alloc.record_payment(
                tenant,
                licenses_granted=licenses_granted,
                amount_inr=amount_inr,
                payment_mode=payment_mode,
                reference_number=str(data.get("referenceNumber") or ""),
                paid_at=_parse_date(data.get("paidAt")),
                notes=str(data.get("notes") or ""),
                idempotency_key=data.get("idempotencyKey") or None,
                invoice=invoice,
                branch_id=data.get("branchId") or None,
                user=request.user,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

        branch_label = ""
        if payment.branch_id:
            branch_label = f" ({payment.branch.name})"
        log_audit(
            category="licensing",
            action="payment_recorded",
            detail=(
                f"₹{amount_inr} for {licenses_granted} license(s){branch_label} "
                f"via {payment_mode} (ref: {data.get('referenceNumber') or '—'})"
            ),
            user=request.user,
            tenant=tenant,
        )
        return Response(
            {
                "payment": payment_dict(payment),
                "summary": alloc.get_summary_dict(tenant),
            },
            status=http.HTTP_201_CREATED,
        )


class PlatformLicensingInvoicesView(APIView):
    """POST /api/v1/organizations/platform/licensing/invoices/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request) -> Response:
        data = request.data
        tenant = _get_tenant(data.get("tenantId"))
        if tenant is None:
            return Response({"error": "School not found."}, status=http.HTTP_404_NOT_FOUND)

        invoice_type = data.get("invoiceType", LicenseInvoiceType.TOP_UP)
        if invoice_type not in LicenseInvoiceType.values:
            return Response({"error": "Invalid invoiceType."}, status=http.HTTP_400_BAD_REQUEST)

        licenses_count = None
        branch_id = data.get("branchId") or None
        if invoice_type != LicenseInvoiceType.RENEWAL:
            try:
                licenses_count = int(data.get("licensesCount", 0))
            except (TypeError, ValueError):
                licenses_count = 0
            if licenses_count <= 0 and branch_id:
                from apps.organizations.models import Branch, StudentLicense
                from apps.organizations.enums import StudentLicenseStatus

                if not Branch.objects.filter(pk=branch_id, tenant=tenant, is_active=True).exists():
                    return Response({"error": "Branch not found for this school."}, status=http.HTTP_400_BAD_REQUEST)
                licenses_count = StudentLicense.objects.filter(
                    tenant=tenant,
                    branch_id=branch_id,
                    license_status=StudentLicenseStatus.UNLICENSED,
                    student_user__is_active=True,
                ).count()
            if licenses_count <= 0:
                return Response(
                    {"error": "licensesCount must be at least 1."},
                    status=http.HTTP_400_BAD_REQUEST,
                )

        notes = str(data.get("notes") or "")
        if branch_id and invoice_type != LicenseInvoiceType.RENEWAL:
            from apps.organizations.models import Branch

            branch = Branch.objects.filter(pk=branch_id, tenant=tenant).first()
            if branch:
                notes = f"Branch: {branch.name}. {notes}".strip()

        invoice = alloc.generate_invoice(
            tenant,
            invoice_type=invoice_type,
            licenses_count=licenses_count,
            notes=notes,
            user=request.user,
        )
        log_audit(
            category="licensing",
            action="invoice_generated",
            detail=f"{invoice_type} invoice: {invoice.licenses_count} × ₹{invoice.unit_price_inr}",
            user=request.user,
            tenant=tenant,
        )
        return Response({"invoice": invoice_dict(invoice)}, status=http.HTTP_201_CREATED)


class PlatformLicensingPeriodView(APIView):
    """PATCH /api/v1/organizations/platform/licensing/periods/<period_id>/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def patch(self, request, period_id) -> Response:
        period = (
            TenantSubscriptionPeriod.objects.select_related("tenant")
            .filter(pk=period_id, is_active=True)
            .first()
        )
        if period is None:
            return Response({"error": "Subscription period not found."}, status=http.HTTP_404_NOT_FOUND)

        new_end = _parse_date(request.data.get("endDate"))
        if new_end is None:
            return Response(
                {"error": "endDate (YYYY-MM-DD) is required."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if new_end <= period.start_date:
            return Response(
                {"error": "endDate must be after the period start date."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        alloc.extend_period(period, new_end, user=request.user)
        log_audit(
            category="licensing",
            action="period_extended",
            detail=f"Subscription end date set to {new_end.isoformat()}",
            user=request.user,
            tenant=period.tenant,
        )
        return Response({"period": period_dict(period)})
