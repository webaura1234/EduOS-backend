"""Django admin for accounts models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import (
    FacultyProfile,
    GuardianProfile,
    InviteToken,
    LoginAttempt,
    OTPRecord,
    RefreshToken,
    StudentGuardianLink,
    StudentProfile,
    User,
)


class RefreshTokenInline(admin.TabularInline):
    model = RefreshToken
    fk_name = "user"
    extra = 0
    can_delete = True
    readonly_fields = (
        "id",
        "token_preview",
        "expires_at",
        "is_revoked",
        "device_info",
        "ip_address",
        "created_at",
    )
    fields = readonly_fields
    ordering = ("-created_at",)

    @admin.display(description="Token (preview)")
    def token_preview(self, obj):
        if not obj.token:
            return "—"
        text = obj.token
        if len(text) > 48:
            text = f"{text[:24]}…{text[-12:]}"
        return text


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin uses email + password (USERNAME_FIELD), not phone/API login."""

    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active", "tenant")
    search_fields = ("email", "first_name", "last_name", "phone", "custom_login_id")
    inlines = (RefreshTokenInline,)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone", "custom_login_id")}),
        ("EduOS", {"fields": ("role", "tenant", "branch", "linked_user_group_id", "must_change_password")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "role",
                    "phone",
                    "custom_login_id",
                    "tenant",
                    "branch",
                    "must_change_password",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    """
    Refresh JWTs persisted on API login (POST /api/v1/auth/login/).

    Access tokens are stateless JWTs — not stored in the database.
    """

    list_display = (
        "user",
        "token_preview",
        "is_revoked",
        "expires_at",
        "is_valid_display",
        "ip_address",
        "created_at",
    )
    list_filter = ("is_revoked", "created_at")
    search_fields = ("user__email", "user__phone", "token", "device_info")
    readonly_fields = (
        "id",
        "user",
        "token",
        "expires_at",
        "is_revoked",
        "device_info",
        "ip_address",
        "created_at",
        "updated_at",
        "is_valid_display",
    )
    raw_id_fields = ("user",)
    ordering = ("-created_at",)

    @admin.display(description="Token (preview)")
    def token_preview(self, obj):
        if not obj.token:
            return "—"
        text = obj.token
        if len(text) > 60:
            text = f"{text[:30]}…{text[-15:]}"
        return text

    @admin.display(boolean=True, description="Valid now")
    def is_valid_display(self, obj):
        return obj.is_valid


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ("phone", "user", "is_used", "expires_at", "attempt_count", "created_at")
    list_filter = ("is_used", "created_at")
    search_fields = ("phone", "user__email")
    readonly_fields = ("id", "otp_hash", "created_at", "updated_at")
    raw_id_fields = ("user",)
    ordering = ("-created_at",)


@admin.register(InviteToken)
class InviteTokenAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "is_used", "expires_at", "sent_to_phone", "created_at")
    list_filter = ("is_used", "created_at")
    search_fields = ("token", "user__email", "sent_to_phone")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("user",)
    ordering = ("-created_at",)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "identifier",
        "tenant",
        "was_successful",
        "failure_reason",
        "ip_address",
        "created_at",
    )
    list_filter = ("was_successful", "failure_reason", "created_at")
    search_fields = ("identifier", "ip_address", "failure_reason")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("tenant",)
    ordering = ("-created_at",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "current_batch", "admission_date")
    search_fields = ("user__email", "user__custom_login_id")
    raw_id_fields = ("user",)


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "designation", "department")
    search_fields = ("user__email", "user__phone")
    raw_id_fields = ("user",)


@admin.register(GuardianProfile)
class GuardianProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "relationship_default", "occupation")
    search_fields = ("user__email", "user__phone")
    raw_id_fields = ("user",)


@admin.register(StudentGuardianLink)
class StudentGuardianLinkAdmin(admin.ModelAdmin):
    list_display = ("student", "guardian", "relationship", "is_primary_contact")
    list_filter = ("relationship", "is_primary_contact")
    raw_id_fields = ("student", "guardian")
