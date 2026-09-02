from pathlib import Path

from django import forms


# ADMIN_IMPORT_UX_V2
class ToolkitImportUploadForm(forms.Form):

    file = forms.FileField(
        label="Choose Excel or CSV file",
        help_text=(
            "Excel (.xlsx) or CSV · Maximum 20 MB"
        ),
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,.csv",
                "class": "bnx-file-input",
            }
        ),
    )


    def clean_file(self):

        uploaded_file = (
            self.cleaned_data["file"]
        )

        max_size = (
            20
            * 1024
            * 1024
        )


        if uploaded_file.size > max_size:

            raise forms.ValidationError(
                "File is larger than the 20 MB limit."
            )


        extension = (
            Path(
                uploaded_file.name
            )
            .suffix
            .lower()
        )


        allowed_extensions = {
            ".xlsx",
            ".csv",
        }


        if (
            extension
            not in allowed_extensions
        ):

            raise forms.ValidationError(
                "Please upload an Excel (.xlsx) "
                "or CSV file."
            )


        return uploaded_file
