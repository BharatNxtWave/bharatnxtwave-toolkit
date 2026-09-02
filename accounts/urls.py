from django.urls import path

from . import auth_views, views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.login_view,
        name="login"
    ),
    path(
        "admin-center/login/",
        auth_views.admin_login_view,
        name="admin_login"
    ),
    path(
        "logout/",
        auth_views.logout_view,
        name="logout"
    ),
    path(
        "session/location/",
        auth_views.session_location_update,
        name="session_location_update"
    ),

    path(
        "employees/",
        views.employee_list,
        name="employee_list"
    ),
    path(
        "employees/add/",
        views.employee_create,
        name="employee_create"
    ),
    path(
        "employees/<int:employee_id>/edit/",
        views.employee_edit,
        name="employee_edit"
    ),
    path(
        "employees/<int:employee_id>/toggle-active/",
        views.employee_toggle_active,
        name="employee_toggle_active"
    ),
    path(
        "employees/<int:employee_id>/password/",
        views.employee_password_reset,
        name="employee_password_reset"
    ),

    path(
        "activity-logs/",
        views.activity_log_list,
        name="activity_logs"
    ),
]
