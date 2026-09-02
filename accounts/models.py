from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("BDE", "BDE"),
        ("DATA_ADMIN", "Data Admin"),
        ("SECURITY_ADMIN", "Security Admin"),
        ("IT_ADMIN", "IT Admin"),
        ("SUPER_ADMIN", "Super Admin"),
    ]

    employee_id = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="BDE",
    )

    department = models.CharField(
        max_length=100,
        blank=True
    )

    is_account_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        if self.employee_id:
            return f"{self.employee_id} - {self.username}"

        return self.username

class LoginSession(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="login_sessions"
    )

    session_key = models.CharField(
        max_length=100,
        blank=True
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    user_agent = models.TextField(
        blank=True
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    location_accuracy = models.FloatField(
        null=True,
        blank=True
    )

    login_at = models.DateTimeField(
        auto_now_add=True
    )

    logout_at = models.DateTimeField(
        null=True,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.login_at}"


class ActivityLog(models.Model):

    ACTION_CHOICES = [
        ("LOGIN", "Login"),
        ("LOGOUT", "Logout"),
        ("EMPLOYEE_CREATE", "Employee Created"),
        ("EMPLOYEE_EDIT", "Employee Updated"),
        ("EMPLOYEE_ACTIVATE", "Employee Activated"),
        ("EMPLOYEE_DEACTIVATE", "Employee Deactivated"),
        ("PASSWORD_RESET", "Password Reset"),
        ("SEARCH", "Toolkit Search"),
        ("FILTER", "Toolkit Filter"),
        ("SERVICE_VIEW", "Service Viewed"),
        ("IMPORT", "Data Import"),
        ("PERMISSION_DENIED", "Permission Denied"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    action = models.CharField(
        max_length=40,
        choices=ACTION_CHOICES
    )

    description = models.CharField(
        max_length=255
    )

    target_type = models.CharField(
        max_length=50,
        blank=True
    )

    target_id = models.CharField(
        max_length=100,
        blank=True
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    user_agent = models.TextField(
        blank=True
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        username = self.user.username if self.user else "Unknown"
        return f"{username} - {self.action} - {self.created_at}"
