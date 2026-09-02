from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .activity import log_activity
from .forms import (
    EmployeeCreateForm,
    EmployeePasswordResetForm,
    EmployeeUpdateForm,
)
from .models import User


def can_manage_employees(user):
    from accounts.portal_access import is_admin_user

    return is_admin_user(user)


def can_edit_employee(actor, employee):
    from accounts.portal_access import is_admin_user

    return is_admin_user(actor)


@user_passes_test(can_manage_employees)
def employee_list(request):
    employees = User.objects.all().order_by(
        "first_name",
        "last_name",
        "username"
    )

    manageable_employee_ids = {
        employee.pk
        for employee in employees
        if can_edit_employee(request.user, employee)
    }

    context = {
        "employees": employees,
        "manageable_employee_ids": manageable_employee_ids,
        "total_employees": employees.count(),
        "active_employees": employees.filter(
            is_account_active=True
        ).count(),
        "bde_count": employees.filter(
            role="BDE",
            is_account_active=True
        ).count(),
    }

    return render(
        request,
        "accounts/employee_list.html",
        context
    )


@user_passes_test(can_manage_employees)
def employee_create(request):
    if request.method == "POST":
        form = EmployeeCreateForm(
            request.POST,
            creator=request.user
        )

        if form.is_valid():
            employee = form.save()

            log_activity(
                request,
                "EMPLOYEE_CREATE",
                f"Created employee account: {employee.username}.",
                target_type="user",
                target_id=employee.pk,
                metadata={
                    "role": employee.role,
                    "employee_id": employee.employee_id or "",
                },
            )

            return redirect("accounts:employee_list")

    else:
        form = EmployeeCreateForm(
            creator=request.user
        )

    return render(
        request,
        "accounts/employee_create.html",
        {"form": form}
    )


@user_passes_test(can_manage_employees)
def employee_edit(request, employee_id):
    employee = get_object_or_404(
        User,
        pk=employee_id
    )

    if not can_edit_employee(request.user, employee):
        return HttpResponseForbidden(
            "You do not have permission to edit this employee."
        )

    if request.method == "POST":
        form = EmployeeUpdateForm(
            request.POST,
            instance=employee,
            editor=request.user
        )

        if form.is_valid():
            employee = form.save()

            log_activity(
                request,
                "EMPLOYEE_EDIT",
                f"Updated employee account: {employee.username}.",
                target_type="user",
                target_id=employee.pk,
                metadata={
                    "role": employee.role,
                    "employee_id": employee.employee_id or "",
                },
            )

            return redirect("accounts:employee_list")

    else:
        form = EmployeeUpdateForm(
            instance=employee,
            editor=request.user
        )

    return render(
        request,
        "accounts/employee_edit.html",
        {
            "form": form,
            "employee": employee,
        }
    )


@require_POST
@user_passes_test(can_manage_employees)
def employee_toggle_active(request, employee_id):
    employee = get_object_or_404(
        User,
        pk=employee_id
    )

    if not can_edit_employee(request.user, employee):
        return HttpResponseForbidden(
            "You do not have permission to modify this employee."
        )

    if employee.pk == request.user.pk:
        return HttpResponseForbidden(
            "You cannot deactivate your own account."
        )

    employee.is_account_active = not employee.is_account_active
    employee.is_active = employee.is_account_active

    employee.save(
        update_fields=[
            "is_account_active",
            "is_active",
        ]
    )

    action = (
        "EMPLOYEE_ACTIVATE"
        if employee.is_account_active
        else "EMPLOYEE_DEACTIVATE"
    )

    state = (
        "activated"
        if employee.is_account_active
        else "deactivated"
    )

    log_activity(
        request,
        action,
        f"{state.capitalize()} employee account: {employee.username}.",
        target_type="user",
        target_id=employee.pk,
    )

    return redirect("accounts:employee_list")


@user_passes_test(can_manage_employees)
def employee_password_reset(request, employee_id):
    employee = get_object_or_404(
        User,
        pk=employee_id
    )

    if not can_edit_employee(request.user, employee):
        return HttpResponseForbidden(
            "You do not have permission to reset this employee's password."
        )

    if employee.pk == request.user.pk:
        return HttpResponseForbidden(
            "You cannot reset your own password from Employee Management."
        )

    if request.method == "POST":
        form = EmployeePasswordResetForm(
            user=employee,
            data=request.POST
        )

        if form.is_valid():
            form.save()

            log_activity(
                request,
                "PASSWORD_RESET",
                f"Reset password for employee: {employee.username}.",
                target_type="user",
                target_id=employee.pk,
            )

            return redirect(
                "accounts:employee_edit",
                employee_id=employee.pk
            )

    else:
        form = EmployeePasswordResetForm(
            user=employee
        )

    return render(
        request,
        "accounts/employee_password_reset.html",
        {
            "form": form,
            "employee": employee,
        }
    )



def can_view_activity_logs(user):
    from accounts.portal_access import is_admin_user

    return is_admin_user(user)


@user_passes_test(can_view_activity_logs)
def activity_log_list(request):
    from .models import ActivityLog

    logs = (
        ActivityLog.objects
        .select_related("user")
        .all()
    )

    action_filter = request.GET.get("action", "").strip()
    search_query = request.GET.get("q", "").strip()

    if action_filter:
        logs = logs.filter(action=action_filter)

    if search_query:
        from django.db.models import Q

        logs = logs.filter(
            Q(description__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(user__employee_id__icontains=search_query)
            | Q(ip_address__icontains=search_query)
        )

    logs = logs[:200]

    return render(
        request,
        "accounts/activity_logs.html",
        {
            "logs": logs,
            "action_choices": ActivityLog.ACTION_CHOICES,
            "selected_action": action_filter,
            "search_query": search_query,
        }
    )
