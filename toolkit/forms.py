from django import forms
from django.utils.text import slugify

from .models import Category, Service, ServiceDomain


class CommaSeparatedListField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "placeholder": "Separate multiple values with commas"
                }
            )
        )
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)

        return value

    def to_python(self, value):
        if not value:
            return []

        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]


class ServiceManagementForm(forms.ModelForm):

    business_types = CommaSeparatedListField()
    business_stages = CommaSeparatedListField()
    industries = CommaSeparatedListField()
    applicable_states = CommaSeparatedListField()
    founder_categories = CommaSeparatedListField()

    class Meta:
        model = Service

        fields = (
            "service_id",
            "title",
            "domain",
            "category",
            "service_kind",
            "status",
            "priority",

            "bde_summary",
            "overview",
            "benefits",
            "restrictions",
            "important_notes",

            "eligibility_summary",
            "business_types",
            "business_stages",
            "industries",
            "applicable_states",
            "founder_categories",

            "min_business_age_months",
            "max_business_age_months",
            "min_turnover",
            "max_turnover",

            "funding_min",
            "funding_max",
            "funding_type",
            "interest_rate_min",
            "interest_rate_max",
            "collateral_required",
            "tenure",
            "subsidy_details",

            "government_fee",
            "bharatnxt_fee",
            "pricing_notes",

            "estimated_processing_time",
            "effective_from",
            "pitch_until",
            "application_deadline",

            "internal_notes",
            "sales_pitch",
            "escalation_notes",
        )

        widgets = {
            "bde_summary": forms.Textarea(
                attrs={"rows": 3}
            ),
            "overview": forms.Textarea(
                attrs={"rows": 5}
            ),
            "benefits": forms.Textarea(
                attrs={"rows": 4}
            ),
            "restrictions": forms.Textarea(
                attrs={"rows": 4}
            ),
            "important_notes": forms.Textarea(
                attrs={"rows": 4}
            ),
            "eligibility_summary": forms.Textarea(
                attrs={"rows": 4}
            ),
            "subsidy_details": forms.Textarea(
                attrs={"rows": 4}
            ),
            "pricing_notes": forms.Textarea(
                attrs={"rows": 3}
            ),
            "internal_notes": forms.Textarea(
                attrs={"rows": 4}
            ),
            "sales_pitch": forms.Textarea(
                attrs={"rows": 4}
            ),
            "escalation_notes": forms.Textarea(
                attrs={"rows": 3}
            ),
            "application_deadline": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["domain"].queryset = (
            ServiceDomain.objects
            .filter(is_active=True)
            .order_by("display_order", "name")
        )

        self.fields["category"].queryset = (
            Category.objects
            .filter(is_active=True)
            .select_related("domain")
            .order_by(
                "domain__display_order",
                "display_order",
                "name"
            )
        )

    def clean(self):
        cleaned = super().clean()

        domain = cleaned.get("domain")
        category = cleaned.get("category")

        if (
            domain
            and category
            and category.domain_id != domain.pk
        ):
            self.add_error(
                "category",
                "Selected category does not belong to this domain."
            )

        return cleaned

    def save(self, commit=True):
        service = super().save(commit=False)

        if not service.slug:
            base_slug = slugify(
                f"{service.service_id}-{service.title}"
            )

            slug = base_slug
            number = 2

            while (
                Service.objects
                .exclude(pk=service.pk)
                .filter(slug=slug)
                .exists()
            ):
                slug = f"{base_slug}-{number}"
                number += 1

            service.slug = slug

        if commit:
            service.save()

        return service
