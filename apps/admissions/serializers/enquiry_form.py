"""Serializers — configurable enquiry form (schema + save payload)."""

from rest_framework import serializers

from apps.admissions.models.enquiry_form import EnquiryFieldType


class EnquiryFieldSerializer(serializers.Serializer):
    """One admin-defined custom field on the enquiry form."""

    key = serializers.SlugField(max_length=50, required=False, allow_blank=True)
    label = serializers.CharField(max_length=120)
    type = serializers.ChoiceField(choices=EnquiryFieldType.choices)
    required = serializers.BooleanField(default=False)
    options = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=False),
        required=False,
        default=list,
    )
    placeholder = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["type"] == EnquiryFieldType.SELECT:
            options = [o.strip() for o in (attrs.get("options") or []) if o.strip()]
            if not options:
                raise serializers.ValidationError(
                    {"options": "Dropdown fields need at least one option."}
                )
            attrs["options"] = options
        else:
            attrs["options"] = []
        return attrs


class SaveEnquiryFormSerializer(serializers.Serializer):
    """PUT payload to replace the whole form definition."""

    title = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=1000, allow_blank=True, default="")
    isPublic = serializers.BooleanField(default=True)
    fields = EnquiryFieldSerializer(many=True)

    def validate_fields(self, value):
        if len(value) > 40:
            raise serializers.ValidationError("A form can have at most 40 custom fields.")
        return value


def enquiry_form_dict(form) -> dict:
    """camelCase representation of a form for admin editing."""
    return {
        "title": form.title,
        "description": form.description,
        "isPublic": form.is_public,
        "fields": form.fields or [],
    }


def public_enquiry_form_dict(form, *, institution_name: str, subdomain: str) -> dict:
    """Read-only schema for the public form page (no internal ids)."""
    return {
        "institutionName": institution_name,
        "subdomain": subdomain,
        "title": form.title,
        "description": form.description,
        "fields": form.fields or [],
    }
