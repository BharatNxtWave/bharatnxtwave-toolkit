from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils.http import (
    url_has_allowed_host_and_scheme,
)
from django.views.decorators.http import require_POST

from accounts.activity import log_activity

from .models import (
    Category,
    SavedService,
    SearchEvent,
    Service,
    ServiceDomain,
)

from .pitching import (
    VISIBLE_STATUSES,
    apply_pitch_state,
    apply_pitch_states,
    available_sectors,
    closing_soon_queryset,
    pitchable_queryset,
    sector_match_ids,
)


def visible_services():
    return pitchable_queryset(
        Service.objects.select_related(
            "domain",
            "category",
            "verified_by",
        )
    )


def all_bde_services():
    return (
        Service.objects
        .select_related(
            "domain",
            "category",
            "verified_by",
        )
        .filter(
            status__in=VISIBLE_STATUSES
        )
    )


def search_text_filter(query):
    return (
        Q(title__icontains=query)
        | Q(service_id__icontains=query)
        | Q(bde_summary__icontains=query)
        | Q(overview__icontains=query)
        | Q(benefits__icontains=query)
        | Q(eligibility_summary__icontains=query)
        | Q(domain__name__icontains=query)
        | Q(category__name__icontains=query)
        | Q(service_kind__icontains=query)
        | Q(funding_type__icontains=query)
        | Q(subsidy_details__icontains=query)
        | Q(sales_pitch__icontains=query)
    )


@login_required
def toolkit_home(request):
    base_services = visible_services()

    query = request.GET.get(
        "q",
        ""
    ).strip()

    sector = request.GET.get(
        "sector",
        ""
    ).strip()

    domain_slug = request.GET.get(
        "domain",
        ""
    ).strip()

    category_id = request.GET.get(
        "category",
        ""
    ).strip()

    service_kind = request.GET.get(
        "kind",
        ""
    ).strip()

    deadline_filter = request.GET.get(
        "deadline",
        ""
    ).strip()


    services = base_services


    # =====================================================
    # SCHEME NAME + NATURAL TEXT + SECTOR SEARCH
    # =====================================================

    if query:
        sector_ids = sector_match_ids(
            base_services,
            query
        )

        services = services.filter(
            search_text_filter(query)
            | Q(pk__in=sector_ids)
        ).distinct()


    # =====================================================
    # DIRECT SECTOR FILTER
    # =====================================================

    if sector:
        sector_ids = sector_match_ids(
            base_services,
            sector
        )

        services = services.filter(
            pk__in=sector_ids
        )


    if domain_slug:
        services = services.filter(
            domain__slug=domain_slug
        )


    if category_id.isdigit():
        services = services.filter(
            category_id=int(
                category_id
            )
        )


    valid_kinds = {
        value
        for value, label
        in Service.SERVICE_KIND_CHOICES
    }

    if service_kind in valid_kinds:
        services = services.filter(
            service_kind=service_kind
        )


    # =====================================================
    # DEADLINE FILTERS
    # =====================================================

    if deadline_filter == "closing":
        services = closing_soon_queryset(
            services,
            days=30
        )

    elif deadline_filter == "urgent":
        services = closing_soon_queryset(
            services,
            days=7
        )

    elif deadline_filter == "no_deadline":
        services = services.filter(
            pitch_until__isnull=True,
            application_deadline__isnull=True,
        )


    result_count = services.count()


    filters = {
        "sector": sector,
        "domain": domain_slug,
        "category": category_id,
        "service_kind": service_kind,
        "deadline": deadline_filter,
    }

    filters_used = any(
        filters.values()
    )


    # =====================================================
    # REAL SEARCH ANALYTICS
    # =====================================================

    if query or filters_used:

        SearchEvent.objects.create(
            user=request.user,

            event_type=(
                "SEARCH"
                if query
                else "FILTER"
            ),

            query=query,

            filters=filters,

            result_count=result_count,
        )


    if query:
        log_activity(
            request,
            "SEARCH",
            f'Toolkit search: "{query}"',
            metadata={
                "query": query,
                "result_count": result_count,
            },
        )


    if filters_used:
        log_activity(
            request,
            "FILTER",
            "Toolkit filters applied.",
            metadata={
                **filters,
                "result_count": result_count,
            },
        )


    domains = (
        ServiceDomain.objects
        .filter(is_active=True)
        .order_by(
            "display_order",
            "name"
        )
    )


    categories = (
        Category.objects
        .filter(is_active=True)
        .select_related("domain")
        .order_by(
            "domain__display_order",
            "display_order",
            "name"
        )
    )


    sector_options = available_sectors(
        base_services
    )


    service_list = list(
        services.order_by(
            "domain__display_order",
            "title"
        )[:100]
    )

    apply_pitch_states(
        service_list
    )


    saved_service_ids = set(
        SavedService.objects
        .filter(user=request.user)
        .values_list(
            "service_id",
            flat=True
        )
    )


    context = {
        "services": service_list,
        "result_count": result_count,

        "domains": domains,
        "categories": categories,
        "sector_options": sector_options,

        "service_kinds": (
            Service.SERVICE_KIND_CHOICES
        ),

        "query": query,
        "selected_sector": sector,
        "selected_domain": domain_slug,
        "selected_category": category_id,
        "selected_kind": service_kind,
        "selected_deadline": deadline_filter,

        "saved_service_ids": (
            saved_service_ids
        ),
    }


    return render(
        request,
        "toolkit/toolkit_home.html",
        context
    )


@login_required
def search_suggestions(request):
    query = request.GET.get(
        "q",
        ""
    ).strip()

    if len(query) < 2:
        return JsonResponse(
            {"results": []}
        )


    base_services = visible_services()

    sector_ids = sector_match_ids(
        base_services,
        query
    )


    services = (
        base_services
        .filter(
            search_text_filter(query)
            | Q(pk__in=sector_ids)
        )
        .distinct()
        .order_by("title")[:8]
    )


    results = []

    for service in services:
        apply_pitch_state(
            service
        )

        results.append(
            {
                "title": service.title,

                "service_id": (
                    service.service_id
                ),

                "domain": (
                    service.domain.name
                ),

                "category": (
                    service.category.name
                ),

                "kind": (
                    service.get_service_kind_display()
                ),

                "url": (
                    f"/toolkit/service/"
                    f"{service.slug}/"
                ),
            }
        )


    return JsonResponse(
        {"results": results}
    )


@login_required
def service_detail(request, slug):
    service = get_object_or_404(
        all_bde_services(),
        slug=slug
    )

    apply_pitch_state(
        service
    )


    log_activity(
        request,
        "SERVICE_VIEW",
        f"Viewed service: {service.title}.",
        target_type="service",
        target_id=service.pk,
        metadata={
            "service_id": service.service_id,
            "domain": service.domain.name,
            "category": service.category.name,
            "pitch_state": (
                service.pitch_state_code
            ),
        },
    )


    is_saved = SavedService.objects.filter(
        user=request.user,
        service=service,
    ).exists()


    return render(
        request,
        "toolkit/service_detail.html",
        {
            "service": service,
            "is_saved": is_saved,
        }
    )


@login_required
def saved_services(request):
    saved_items = list(
        SavedService.objects
        .filter(user=request.user)
        .select_related(
            "service",
            "service__domain",
            "service__category",
        )
        .order_by("-created_at")
    )

    for item in saved_items:
        apply_pitch_state(
            item.service
        )


    return render(
        request,
        "toolkit/saved_services.html",
        {
            "saved_items": saved_items,
        }
    )


@login_required
@require_POST
def toggle_saved_service(
    request,
    service_id
):
    service = get_object_or_404(
        Service,
        pk=service_id,
        status__in=VISIBLE_STATUSES,
    )


    saved_item = SavedService.objects.filter(
        user=request.user,
        service=service,
    ).first()


    if saved_item:
        saved_item.delete()

        saved = False

        if (
            request.headers.get(
                "X-Requested-With"
            )
            != "XMLHttpRequest"
        ):
            messages.success(
                request,
                f'Removed "{service.title}" from Saved Services.'
            )

        log_activity(
            request,
            "SERVICE_UNSAVE",
            (
                "Removed saved service: "
                f"{service.title}."
            ),
            target_type="service",
            target_id=service.pk,
            metadata={
                "service_id": (
                    service.service_id
                ),
            },
        )

    else:
        SavedService.objects.create(
            user=request.user,
            service=service,
        )

        saved = True

        if (
            request.headers.get(
                "X-Requested-With"
            )
            != "XMLHttpRequest"
        ):
            messages.success(
                request,
                f'Saved "{service.title}" to Saved Services.'
            )

        log_activity(
            request,
            "SERVICE_SAVE",
            (
                "Saved service: "
                f"{service.title}."
            ),
            target_type="service",
            target_id=service.pk,
            metadata={
                "service_id": (
                    service.service_id
                ),
            },
        )


    if (
        request.headers.get(
            "X-Requested-With"
        )
        == "XMLHttpRequest"
    ):
        return JsonResponse(
            {
                "saved": saved,
                "service_id": service.pk,
            }
        )


    next_url = request.POST.get(
        "next",
        ""
    )

    if (
        next_url
        and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={
                request.get_host()
            },
            require_https=request.is_secure(),
        )
    ):
        return redirect(
            next_url
        )


    return redirect(
        "toolkit:service_detail",
        slug=service.slug
    )
