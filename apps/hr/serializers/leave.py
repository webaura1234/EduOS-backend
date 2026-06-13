"""Serializers — leave balances + applications (camelCase I/O)."""

from rest_framework import serializers

from apps.hr.enums import LeaveType


class LeaveBalanceSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    employeeId = serializers.UUIDField(source="employee_id", read_only=True)
    leaveType = serializers.CharField(source="leave_type", read_only=True)
    year = serializers.CharField(read_only=True)
    balanceDays = serializers.DecimalField(source="balance_days", max_digits=6, decimal_places=2,
                                           read_only=True)


class LeaveApplicationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    employeeId = serializers.UUIDField(source="employee_id", read_only=True)
    leaveType = serializers.CharField(source="leave_type", read_only=True)
    fromDate = serializers.DateField(source="from_date", read_only=True)
    toDate = serializers.DateField(source="to_date", read_only=True)
    days = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    reason = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    approverId = serializers.UUIDField(source="approver_id", read_only=True, allow_null=True)
    autoRoutedCoi = serializers.BooleanField(source="auto_routed_coi", read_only=True)
    version = serializers.IntegerField(read_only=True)


class ApplyLeaveSerializer(serializers.Serializer):
    employeeId = serializers.UUIDField()
    leaveType = serializers.ChoiceField(choices=LeaveType.values)
    fromDate = serializers.DateField()
    toDate = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class DecideLeaveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False)
