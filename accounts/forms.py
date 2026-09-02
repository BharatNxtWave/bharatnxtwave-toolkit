from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm

from .models import User


class EmployeeCreateForm(UserCreationForm):

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "employee_id",
            "email",
            "department",
            "role",
            "is_account_active",
        )

    def __init__(self, *args, creator=None, **kwargs):
        super().__init__(*args, **kwargs)


    def save(self, commit=True):
        user = super().save(commit=False)

        # Keep business account status and Django login status synchronized.
        user.is_active = user.is_account_active

        if commit:
            user.save()

        return user


class EmployeeUpdateForm(forms.ModelForm):

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "employee_id",
            "email",
            "department",
            "role",
            "is_account_active",
        )

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)


        # Prevent an admin from accidentally locking out
        # their own currently signed-in account.
        if (
            editor
            and self.instance
            and self.instance.pk
            and self.instance.pk == editor.pk
        ):
            self.fields["is_account_active"].disabled = True
            self.fields["is_account_active"].help_text = (
                "Your own signed-in account cannot be deactivated here."
            )

    def save(self, commit=True):
        user = super().save(commit=False)

        user.is_active = user.is_account_active

        if commit:
            user.save()

        return user


class EmployeePasswordResetForm(SetPasswordForm):
    pass
