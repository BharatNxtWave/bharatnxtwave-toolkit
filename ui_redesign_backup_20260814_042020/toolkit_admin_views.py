from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.activity import log_activity

from .forms import ServiceManagementForm
from .models import Service, ServiceDomain


def can_manage_toolkit(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.role in {
                "SUPER_ADMIN",
                "DATA_ADMIN",
            }
        )
    )


@user_passes_test(can_manage_toolkit)
def service_management_list(request):
    services = (
        Service.objects
        .select_related(
            "domain",
            "category",
            "verified_by",
        )
        .all()
    )

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    domain = request.GET.get("domain", "").strip()

    if query:
        services = services.filter(
            Q(title__icontains=query)
            | Q(service_id__icontains=query)
            | Q(category__name__icontains=query)
            | Q(domain__name__icontains=query)
        )

    valid_statuses = {
        value
        for value, label
        in Service.STATUS_CHOICES
    }

    if status in valid_statuses:
        services = services.filter(status=status)

    if domain:
        services = services.filter(
            domain__slug=domain
        )

    context = {
        "services": services.order_by("title")[:250],
        "query": query,
        "selected_status": status,
        "selected_domain": domain,
        "status_choices": Service.STATUS_CHOICES,
        "domains": (
            ServiceDomain.objects
            .filter(is_active=True)
            .order_by("display_order", "name")
        ),
    }

    return render(
        request,
        "toolkit/admin/service_list.html",
        context
    )


@user_passes_test(can_manage_toolkit)
def service_create(request):
    if request.method == "POST":
        form = ServiceManagementForm(
            request.POST
        )

        if form.is_valid():
            service = form.save(commit=False)
            service.created_by = request.user
            service.save()

            log_activity(
                request,
                "IMPORT",
                f"Created toolkit service: {service.title}.",
                target_type="service",
                target_id=service.pk,
                metadata={
                    "operation": "manual_create",
                    "service_id": service.service_id,
                },
            )

            return redirect(
                "toolkit:admin_service_list"
            )

    else:
        form = ServiceManagementForm()

    return render(
        request,
        "toolkit/admin/service_form.html",
        {
            "form": form,
            "page_mode": "create",
            "service": None,
        }
    )


@user_passes_test(can_manage_toolkit)
def service_edit(request, service_id):
    service = get_object_or_404(
        Service,
        pk=service_id
    )

    if request.method == "POST":
        form = ServiceManagementForm(
            request.POST,
            instance=service
        )

        if form.is_valid():
            service = form.save()

            log_activity(
                request,
                "IMPORT",
                f"Updated toolkit service: {service.title}.",
                target_type="service",
                target_id=service.pk,
                metadata={
                    "operation": "manual_update",
                    "service_id": service.service_id,
                },
            )

            return redirect(
                "toolkit:admin_service_list"
            )

    else:
        form = ServiceManagementForm(
            instance=service
        )

    return render(
        request,
        "toolkit/admin/service_form.html",
        {
            "form": form,
            "page_mode": "edit",
            "service": service,
        }
    )


@user_passes_test(can_manage_toolkit)
def service_verify(request, service_id):
    service = get_object_or_404(
        Service,
        pk=service_id
    )

    if request.method != "POST":
        return redirect(
            "toolkit:admin_service_list"
        )

    service.last_verified_at = timezone.now()
    service.verified_by = request.user

    service.save(
        update_fields=[
            "last_verified_at",
            "verified_by",
        ]
    )

    log_activity(
        request,
        "IMPORT",
        f"Verified toolkit service: {service.title}.",
        target_type="service",
        target_id=service.pk,
        metadata={
            "operation": "verify",
            "service_id": service.service_id,
        },
    )

    return redirect(
        "toolkit:admin_service_list"
    )


# =========================================================
# PITCH WINDOW MANAGEMENT / MONITORING
# =========================================================

def can_view_pitch_windows(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.role in {
                "SUPER_ADMIN",
                "DATA_ADMIN",
                "IT_ADMIN",
            }
        )
    )


from django.contrib.auth.decorators import user_passes_test as _pitch_user_passes_test


@_pitch_user_passes_test(
    can_view_pitch_windows
)
def pitch_window_list(request):
    from django.db.models import Q
    from django.shortcuts import render

    from .models import Service
    from .pitching import (
        VISIBLE_STATUSES,
        apply_pitch_states,
    )

    query = request.GET.get(
        "q",
        ""
    ).strip()

    selected_state = request.GET.get(
        "state",
        "active"
    ).strip()


    services = (
        Service.objects
        .select_related(
            "domain",
            "category",
        )
        .filter(
            status__in=VISIBLE_STATUSES
        )
    )


    if query:
        services = services.filter(
            Q(title__icontains=query)
            | Q(service_id__icontains=query)
            | Q(domain__name__icontains=query)
        )


    service_list = list(
        services.order_by(
            "pitch_until",
            "application_deadline",
            "title",
        )
    )

    apply_pitch_states(
        service_list
    )


    all_rows = service_list


    if selected_state == "closing":
        service_list = [
            service
            for service in all_rows
            if service.pitch_state_code
            in {
                "URGENT",
                "CLOSING",
            }
        ]

    elif selected_state == "urgent":
        service_list = [
            service
            for service in all_rows
            if service.pitch_state_code
            == "URGENT"
        ]

    elif selected_state == "upcoming":
        service_list = [
            service
            for service in all_rows
            if service.pitch_state_code
            == "UPCOMING"
        ]

    elif selected_state == "closed":
        service_list = [
            service
            for service in all_rows
            if service.pitch_state_code
            == "CLOSED"
        ]

    elif selected_state == "all":
        service_list = all_rows

    else:
        service_list = [
            service
            for service in all_rows
            if service.is_pitchable_now
        ]


    context = {
        "services": service_list[:300],

        "query": query,
        "selected_state": selected_state,

        "active_count": sum(
            1
            for service in all_rows
            if service.is_pitchable_now
        ),

        "closing_count": sum(
            1
            for service in all_rows
            if service.pitch_state_code
            in {
                "URGENT",
                "CLOSING",
            }
        ),

        "urgent_count": sum(
            1
            for service in all_rows
            if service.pitch_state_code
            == "URGENT"
        ),

        "upcoming_count": sum(
            1
            for service in all_rows
            if service.pitch_state_code
            == "UPCOMING"
        ),

        "closed_count": sum(
            1
            for service in all_rows
            if service.pitch_state_code
            == "CLOSED"
        ),
    }


    return render(
        request,
        "toolkit/admin/pitch_windows.html",
        context
    )
