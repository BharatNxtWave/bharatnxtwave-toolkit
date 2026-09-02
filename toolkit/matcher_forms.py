from django import forms

from .models import Service


class ClientMatcherForm(forms.Form):

    need_query = forms.CharField(
        required=False,
        max_length=200,
        label="What is the client looking for?",
        widget=forms.TextInput(
            attrs={
                "placeholder": (
                    "e.g. technology schemes, seed funding, "
                    "MSME loan, Startup India..."
                ),
                "autocomplete": "off",
            }
        ),
    )

    industry = forms.CharField(
        required=False,
        max_length=150,
        label="Industry / Sector",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Technology, SaaS, Manufacturing",
                "autocomplete": "off",
            }
        ),
    )

    business_stage = forms.CharField(
        required=False,
        max_length=120,
        label="Business Stage",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Early Stage, Growth Stage",
                "autocomplete": "off",
            }
        ),
    )

    state = forms.CharField(
        required=False,
        max_length=120,
        label="State",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Uttar Pradesh",
                "autocomplete": "off",
            }
        ),
    )

    business_type = forms.CharField(
        required=False,
        max_length=120,
        label="Business Type",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Pvt Ltd, LLP, Proprietorship",
                "autocomplete": "off",
            }
        ),
    )

    founder_category = forms.CharField(
        required=False,
        max_length=120,
        label="Founder Category",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Women, SC/ST, General",
                "autocomplete": "off",
            }
        ),
    )

    business_age_years = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=100,
        decimal_places=2,
        label="Business Age",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g. 2",
                "step": "0.1",
            }
        ),
    )

    turnover_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=2,
        label="Annual Turnover",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g. 80",
                "step": "0.01",
            }
        ),
    )

    turnover_unit = forms.ChoiceField(
        required=False,
        initial="LAKH",
        choices=[
            ("LAKH", "Lakh"),
            ("CRORE", "Crore"),
            ("RUPEES", "₹ Rupees"),
        ],
    )

    service_kinds = forms.MultipleChoiceField(
        required=False,
        label="Specific service types",
        choices=Service.SERVICE_KIND_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
