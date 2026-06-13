"""Serializers — salary components, payroll runs, payslips, adjustments (camelCase I/O)."""

from rest_framework import serializers

from apps.fees.helpers.paise import paise_to_rupees_str
from apps.hr.enums import ComponentCalc, ComponentKind


class SalaryComponentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    calc = serializers.CharField(read_only=True)
    amountPaise = serializers.IntegerField(source="amount_paise", read_only=True)
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)


class CreateSalaryComponentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    kind = serializers.ChoiceField(choices=ComponentKind.values)
    calc = serializers.ChoiceField(choices=ComponentCalc.values, default=ComponentCalc.FIXED)
    amountPaise = serializers.IntegerField(required=False, default=0)
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)


class PayrollRunSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    periodMonth = serializers.DateField(source="period_month", read_only=True)
    status = serializers.CharField(read_only=True)
    isLocked = serializers.BooleanField(source="is_locked", read_only=True)
    totals = serializers.JSONField(read_only=True)
    executedAt = serializers.DateTimeField(source="executed_at", read_only=True, allow_null=True)


class RunPayrollSerializer(serializers.Serializer):
    periodMonth = serializers.DateField()


class PayslipSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    payrollRunId = serializers.UUIDField(source="payroll_run_id", read_only=True)
    employeeId = serializers.UUIDField(source="employee_id", read_only=True)
    name = serializers.CharField(source="employee.user.full_name", read_only=True)
    components = serializers.JSONField(read_only=True)
    grossPaise = serializers.IntegerField(source="gross_paise", read_only=True)
    deductionsPaise = serializers.IntegerField(source="deductions_paise", read_only=True)
    netPaise = serializers.IntegerField(source="net_paise", read_only=True)
    grossRupees = serializers.SerializerMethodField()
    netRupees = serializers.SerializerMethodField()
    workedDays = serializers.DecimalField(source="worked_days", max_digits=5, decimal_places=2,
                                          read_only=True)
    payableDays = serializers.DecimalField(source="payable_days", max_digits=5, decimal_places=2,
                                           read_only=True)
    proRated = serializers.BooleanField(source="pro_rated", read_only=True)
    pdfKey = serializers.CharField(source="pdf_key", read_only=True)

    def get_grossRupees(self, obj):
        return paise_to_rupees_str(obj.gross_paise)

    def get_netRupees(self, obj):
        return paise_to_rupees_str(obj.net_paise)


class CreateAdjustmentSerializer(serializers.Serializer):
    employeeId = serializers.UUIDField()
    originalRunId = serializers.UUIDField(required=False, allow_null=True)
    amountPaise = serializers.IntegerField()
    reason = serializers.CharField()
