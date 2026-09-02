from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import LoginSession, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "BharatNXT Wave Employee Information",
            {
                "fields": (
                    "employee_id",
                    "role",
                    "department",
                    "is_account_active",
                )
            },
        ),
    )
    
    list_display = (
        "username",
        "employee_id",
        "role",
        "department",
        "is_account_active",
        "is_staff",
    )
    
    list_filter = (
        "role",
        "department",
        "is_account_active",
        "is_staff",
    )
    
    search_fields = (
        "username",
        "employee_id",
        "first_name",
        "last_name",
        "email",
    )


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ip_address",
        "login_at",
        "logout_at",
        "is_active",
    )

    list_filter = (
        "is_active",
        "login_at",
    )

    search_fields = (
        "user__username",
        "user__employee_id",
        "ip_address",
        "user_agent",
    )

    readonly_fields = (
        "user",
        "session_key",
        "ip_address",
        "user_agent",
        "latitude",
        "longitude",
        "location_accuracy",
        "login_at",
        "logout_at",
        "is_active",
    )

    ordering = (
        "-login_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
