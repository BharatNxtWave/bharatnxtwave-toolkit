from __future__ import annotations

from django import forms

from .flyer_validation import inspect_flyer_upload


class ServiceFlyerUploadForm(forms.Form):
    flyer = forms.FileField(
        label="Select flyer",
        help_text="PDF, JPG, JPEG or PNG. Maximum 20 MB.",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png",
                "data-flyer-file": "",
            }
        ),
    )

    update_note = forms.CharField(
        label="Update note",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "Optional: what changed in this flyer?"
                ),
            }
        ),
    )

    service_confirmation = forms.CharField(
        widget=forms.HiddenInput(),
    )

    def clean_flyer(self):
        uploaded_file = self.cleaned_data["flyer"]
        self.flyer_metadata = inspect_flyer_upload(uploaded_file)
        return uploaded_file
