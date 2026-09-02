import calendar
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from accounts.models import ActivityLog, LoginSession, User
from toolkit.models import (
    SavedService,
    SearchEvent,
    Service,
    ServiceDomain,
)

from toolkit.pitching import (
    apply_pitch_states,
    closing_soon_queryset,
)


VISIBLE_STATUSES = [
    "APPROVED",
    "PUBLISHED",
    "EXPIRING",
]


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return None


def build_calendar(
    user,
    year,
    month,
    selected_start,
    selected_end,
):
    cal = calendar.Calendar(
        firstweekday=0
    )

    month_dates = list(
        cal.itermonthdates(
            year,
            month
        )
    )

    calendar_start = month_dates[0]
    calendar_end = month_dates[-1]

    search_rows = (
        SearchEvent.objects
        .filter(
            user=user,
            event_type="SEARCH",
            created_at__date__range=(
                calendar_start,
                calendar_end,
            )
        )
        .values("created_at__date")
        .annotate(total=Count("id"))
    )

    search_counts = {
        row["created_at__date"]: row["total"]
        for row in search_rows
    }

    today = timezone.localdate()

    weeks = []

    for week_start in range(
        0,
        len(month_dates),
        7
    ):
        week = []

        for day in month_dates[
            week_start:week_start + 7
        ]:
            selected = (
                selected_start
                <= day
                <= selected_end
            )

            week.append(
                {
                    "date": day,
                    "date_value": day.isoformat(),
                    "day": day.day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "selected": selected,
                    "search_count": search_counts.get(
                        day,
                        0
                    ),
                }
            )

        weeks.append(week)

    return weeks


@login_required
def home(request):
    today = timezone.localdate()

    preset = request.GET.get(
        "preset",
        ""
    ).strip()

    selected_start = parse_date(
        request.GET.get("start")
    )

    selected_end = parse_date(
        request.GET.get("end")
    )


    # =====================================================
    # DATE RANGE
    # =====================================================

    if preset == "today":
        selected_start = today
        selected_end = today

    elif preset == "7d":
        selected_start = today - timedelta(days=6)
        selected_end = today

    elif preset == "30d":
        selected_start = today - timedelta(days=29)
        selected_end = today


    if not selected_start:
        selected_start = today - timedelta(days=6)

    if not selected_end:
        selected_end = today

    if selected_end < selected_start:
        selected_start, selected_end = (
            selected_end,
            selected_start,
        )

    # Prevent accidental huge analytics ranges.
    if (
        selected_end - selected_start
    ).days > 365:
        selected_start = (
            selected_end
            - timedelta(days=365)
        )


    # =====================================================
    # CALENDAR MONTH
    # =====================================================

    month_value = request.GET.get(
        "month",
        ""
    ).strip()

    try:
        if month_value:
            calendar_month_date = datetime.strptime(
                month_value,
                "%Y-%m"
            ).date()

            calendar_year = (
                calendar_month_date.year
            )

            calendar_month = (
                calendar_month_date.month
            )

        else:
            calendar_year = selected_end.year
            calendar_month = selected_end.month

    except ValueError:
        calendar_year = today.year
        calendar_month = today.month


    first_of_month = date(
        calendar_year,
        calendar_month,
        1
    )

    previous_month_date = (
        first_of_month
        - timedelta(days=1)
    ).replace(day=1)

    if calendar_month == 12:
        next_month_date = date(
            calendar_year + 1,
            1,
            1
        )
    else:
        next_month_date = date(
            calendar_year,
            calendar_month + 1,
            1
        )


    calendar_weeks = build_calendar(
        request.user,
        calendar_year,
        calendar_month,
        selected_start,
        selected_end,
    )


    # =====================================================
    # STRUCTURED SEARCH ANALYTICS
    # =====================================================

    period_events = SearchEvent.objects.filter(
        user=request.user,
        created_at__date__range=(
            selected_start,
            selected_end,
        )
    )

    search_events = period_events.filter(
        event_type="SEARCH"
    )

    filter_events = period_events.filter(
        event_type="FILTER"
    )

    search_count = search_events.count()

    filter_count = filter_events.count()

    zero_result_count = search_events.filter(
        result_count=0
    ).count()

    services_viewed = (
        ActivityLog.objects
        .filter(
            user=request.user,
            action="SERVICE_VIEW",
            created_at__date__range=(
                selected_start,
                selected_end,
            )
        )
        .count()
    )

    saved_count = SavedService.objects.filter(
        user=request.user
    ).count()

    available_services = Service.objects.filter(
        status__in=VISIBLE_STATUSES
    ).count()


    # =====================================================
    # ACTIVITY CHART
    # =====================================================

    activity_chart = []

    number_of_days = (
        selected_end - selected_start
    ).days + 1

    for offset in range(number_of_days):
        day = (
            selected_start
            + timedelta(days=offset)
        )

        count = search_events.filter(
            created_at__date=day
        ).count()

        activity_chart.append(
            {
                "date": day,
                "date_value": day.isoformat(),
                "label": day.strftime("%d %b"),
                "count": count,
            }
        )

    max_searches = max(
        [
            item["count"]
            for item in activity_chart
        ]
        or [1]
    )

    if max_searches == 0:
        max_searches = 1

    for item in activity_chart:
        item["height"] = max(
            4,
            round(
                (
                    item["count"]
                    / max_searches
                )
                * 100
            )
        )


    # =====================================================
    # TOP QUERIES
    # =====================================================

    top_query_rows = (
        search_events
        .exclude(query="")
        .values("query")
        .annotate(total=Count("id"))
        .order_by("-total", "query")[:6]
    )

    top_queries = list(
        top_query_rows
    )


    # =====================================================
    # RECENT SEARCHES
    # =====================================================

    recent_searches = (
        search_events
        .exclude(query="")
        .order_by("-created_at")[:6]
    )


    # =====================================================
    # RECENT SERVICE VIEWS
    # =====================================================

    recent_view_logs = list(
        ActivityLog.objects
        .filter(
            user=request.user,
            action="SERVICE_VIEW",
            created_at__date__range=(
                selected_start,
                selected_end,
            )
        )
        .order_by("-created_at")[:6]
    )

    service_ids = [
        int(log.target_id)
        for log in recent_view_logs
        if str(log.target_id).isdigit()
    ]

    service_map = {
        service.pk: service
        for service
        in Service.objects.filter(
            pk__in=service_ids
        )
    }

    recent_views = []

    for log in recent_view_logs:
        service = None

        if str(log.target_id).isdigit():
            service = service_map.get(
                int(log.target_id)
            )

        recent_views.append(
            {
                "service": service,
                "description": log.description,
                "created_at": log.created_at,
            }
        )


    # =====================================================
    # DOMAIN COVERAGE
    # =====================================================

    domains = (
        ServiceDomain.objects
        .filter(is_active=True)
        .annotate(
            visible_service_count=Count(
                "services",
                filter=Q(
                    services__status__in=VISIBLE_STATUSES
                )
            )
        )
        .order_by(
            "display_order",
            "name"
        )
    )


    closing_soon_services = list(
        closing_soon_queryset(
            Service.objects
            .select_related(
                "domain",
                "category",
            ),
            days=30,
        )
        .order_by(
            "pitch_until",
            "application_deadline",
            "title",
        )[:6]
    )

    apply_pitch_states(
        closing_soon_services
    )


    # =====================================================
    # REAL DAILY TOOLKIT ACTIVITY
    # Search + Client Matcher
    # =====================================================

    activity_rows = (
        SearchEvent.objects
        .filter(
            user=request.user,
            created_at__date__range=(
                selected_start,
                selected_end,
            ),
            event_type__in=[
                "SEARCH",
                "CLIENT_MATCH",
            ],
        )
        .values(
            "created_at__date",
            "event_type",
        )
        .annotate(
            event_count=Count("id")
        )
    )


    activity_lookup = {}

    for row in activity_rows:

        day = row["created_at__date"]

        if day not in activity_lookup:
            activity_lookup[day] = {
                "SEARCH": 0,
                "CLIENT_MATCH": 0,
            }

        activity_lookup[day][
            row["event_type"]
        ] = row["event_count"]


    daily_activity_chart = []

    current_day = selected_start

    while current_day <= selected_end:

        counts = activity_lookup.get(
            current_day,
            {
                "SEARCH": 0,
                "CLIENT_MATCH": 0,
            },
        )

        search_count = counts.get(
            "SEARCH",
            0
        )

        matcher_count = counts.get(
            "CLIENT_MATCH",
            0
        )

        daily_activity_chart.append(
            {
                "date": current_day,

                "label": current_day.strftime(
                    "%d %b"
                ),

                "search_count": search_count,

                "matcher_count": matcher_count,

                "total_count": (
                    search_count
                    + matcher_count
                ),
            }
        )

        current_day += timedelta(
            days=1
        )


    max_activity_count = max(
        [
            max(
                day["search_count"],
                day["matcher_count"],
            )
            for day
            in daily_activity_chart
        ],
        default=0,
    )

    max_activity_count = max(
        max_activity_count,
        1
    )


    for day in daily_activity_chart:

        day["search_height"] = (
            round(
                (
                    day["search_count"]
                    / max_activity_count
                )
                * 100,
                2,
            )
            if day["search_count"]
            else 0
        )

        day["matcher_height"] = (
            round(
                (
                    day["matcher_count"]
                    / max_activity_count
                )
                * 100,
                2,
            )
            if day["matcher_count"]
            else 0
        )

        # Backward compatibility
        day["count"] = day[
            "search_count"
        ]

        day["height"] = day[
            "search_height"
        ]


    context = {
        "daily_activity_chart": daily_activity_chart,
        "closing_soon_services": closing_soon_services,
        "selected_start": selected_start,
        "selected_end": selected_end,
        "preset": preset,

        "calendar_weeks": calendar_weeks,
        "calendar_title": first_of_month.strftime(
            "%B %Y"
        ),
        "calendar_month_value": first_of_month.strftime(
            "%Y-%m"
        ),
        "previous_month": previous_month_date.strftime(
            "%Y-%m"
        ),
        "next_month": next_month_date.strftime(
            "%Y-%m"
        ),

        "search_count": search_count,
        "filter_count": filter_count,
        "zero_result_count": zero_result_count,
        "services_viewed": services_viewed,
        "saved_count": saved_count,
        "available_services": available_services,

        "activity_chart": activity_chart,
        "top_queries": top_queries,
        "recent_searches": recent_searches,
        "recent_views": recent_views,
        "domains": domains,
    }

    return render(
        request,
        "dashboard/home.html",
        context
    )


def can_access_admin_center(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.role in {
                "SUPER_ADMIN",
                "IT_ADMIN",
                "DATA_ADMIN",
                "SECURITY_ADMIN",
            }
        )
    )


@user_passes_test(can_access_admin_center)
def admin_overview(request):
    employees = User.objects.all()
    services = Service.objects.all()

    context = {
        "total_employees": employees.count(),

        "active_employees": employees.filter(
            is_account_active=True
        ).count(),

        "total_services": services.count(),

        "published_services": services.filter(
            status__in=VISIBLE_STATUSES
        ).count(),

        "active_sessions": LoginSession.objects.filter(
            is_active=True
        ).count(),

        "recent_activity": (
            ActivityLog.objects
            .select_related("user")
            .all()[:8]
        ),
    }

    return render(
        request,
        "dashboard/admin_overview.html",
        context
    )


# =========================================================
# ADMIN BDE ANALYTICS
# =========================================================

def can_view_bde_analytics(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.role in {
                "SUPER_ADMIN",
                "IT_ADMIN",
                "SECURITY_ADMIN",
            }
        )
    )


@user_passes_test(can_view_bde_analytics)
def bde_analytics(request):
    today = timezone.localdate()

    bdes = (
        User.objects
        .filter(
            role="BDE"
        )
        .order_by(
            "first_name",
            "last_name",
            "username",
        )
    )

    employee_id = request.GET.get(
        "employee",
        ""
    ).strip()

    selected_bde = None

    if employee_id.isdigit():
        selected_bde = bdes.filter(
            pk=int(employee_id)
        ).first()

    if not selected_bde:
        selected_bde = bdes.first()


    # No BDE accounts exist yet.
    if not selected_bde:
        return render(
            request,
            "dashboard/bde_analytics.html",
            {
                "bdes": bdes,
                "selected_bde": None,
            }
        )


    # =====================================================
    # DATE RANGE
    # =====================================================

    preset = request.GET.get(
        "preset",
        ""
    ).strip()

    selected_start = parse_date(
        request.GET.get("start")
    )

    selected_end = parse_date(
        request.GET.get("end")
    )

    if preset == "today":
        selected_start = today
        selected_end = today

    elif preset == "7d":
        selected_start = today - timedelta(days=6)
        selected_end = today

    elif preset == "30d":
        selected_start = today - timedelta(days=29)
        selected_end = today

    if not selected_start:
        selected_start = today - timedelta(days=6)

    if not selected_end:
        selected_end = today

    if selected_end < selected_start:
        selected_start, selected_end = (
            selected_end,
            selected_start,
        )

    if (
        selected_end - selected_start
    ).days > 365:
        selected_start = (
            selected_end
            - timedelta(days=365)
        )


    # =====================================================
    # CALENDAR MONTH
    # =====================================================

    month_value = request.GET.get(
        "month",
        ""
    ).strip()

    try:
        if month_value:
            month_date = datetime.strptime(
                month_value,
                "%Y-%m"
            ).date()

            calendar_year = month_date.year
            calendar_month = month_date.month

        else:
            calendar_year = selected_end.year
            calendar_month = selected_end.month

    except ValueError:
        calendar_year = today.year
        calendar_month = today.month

    first_of_month = date(
        calendar_year,
        calendar_month,
        1
    )

    previous_month_date = (
        first_of_month
        - timedelta(days=1)
    ).replace(day=1)

    if calendar_month == 12:
        next_month_date = date(
            calendar_year + 1,
            1,
            1
        )
    else:
        next_month_date = date(
            calendar_year,
            calendar_month + 1,
            1
        )

    calendar_weeks = build_calendar(
        selected_bde,
        calendar_year,
        calendar_month,
        selected_start,
        selected_end,
    )


    # =====================================================
    # SEARCH EVENTS
    # =====================================================

    period_events = SearchEvent.objects.filter(
        user=selected_bde,
        created_at__date__range=(
            selected_start,
            selected_end,
        )
    )

    search_events = period_events.filter(
        event_type="SEARCH"
    )

    filter_events = period_events.filter(
        event_type="FILTER"
    )

    searches = search_events.count()

    filters = filter_events.count()

    zero_results = search_events.filter(
        result_count=0
    ).count()

    successful_searches = search_events.filter(
        result_count__gt=0
    ).count()

    unique_queries = (
        search_events
        .exclude(query="")
        .values("query")
        .distinct()
        .count()
    )


    # =====================================================
    # OTHER USER ACTIVITY
    # =====================================================

    activity = ActivityLog.objects.filter(
        user=selected_bde,
        created_at__date__range=(
            selected_start,
            selected_end,
        )
    )

    service_views = activity.filter(
        action="SERVICE_VIEW"
    ).count()

    saves = activity.filter(
        action="SERVICE_SAVE"
    ).count()

    unsaves = activity.filter(
        action="SERVICE_UNSAVE"
    ).count()

    current_saved = SavedService.objects.filter(
        user=selected_bde
    ).count()

    login_count = activity.filter(
        action="LOGIN"
    ).count()

    active_sessions = LoginSession.objects.filter(
        user=selected_bde,
        is_active=True
    ).count()


    # =====================================================
    # DAILY CHART DATA
    # =====================================================

    chart = []

    days = (
        selected_end - selected_start
    ).days + 1

    for offset in range(days):
        day = (
            selected_start
            + timedelta(days=offset)
        )

        day_searches = search_events.filter(
            created_at__date=day
        ).count()

        day_views = activity.filter(
            action="SERVICE_VIEW",
            created_at__date=day
        ).count()

        chart.append(
            {
                "date": day,
                "date_value": day.isoformat(),
                "label": day.strftime("%d %b"),
                "searches": day_searches,
                "views": day_views,
            }
        )

    max_chart_value = max(
        [
            max(
                item["searches"],
                item["views"]
            )
            for item in chart
        ]
        or [1]
    )

    if max_chart_value == 0:
        max_chart_value = 1

    for item in chart:
        item["search_height"] = max(
            4,
            round(
                (
                    item["searches"]
                    / max_chart_value
                ) * 100
            )
        )

        item["view_height"] = max(
            4,
            round(
                (
                    item["views"]
                    / max_chart_value
                ) * 100
            )
        )


    # =====================================================
    # TOP SEARCH QUERIES
    # =====================================================

    top_queries = list(
        search_events
        .exclude(query="")
        .values("query")
        .annotate(total=Count("id"))
        .order_by("-total", "query")[:8]
    )


    # =====================================================
    # ZERO-RESULT QUERIES
    # Very useful: identifies missing toolkit coverage.
    # =====================================================

    zero_result_queries = list(
        search_events
        .filter(result_count=0)
        .exclude(query="")
        .values("query")
        .annotate(total=Count("id"))
        .order_by("-total", "query")[:8]
    )


    # =====================================================
    # MOST VIEWED SERVICES
    # =====================================================

    viewed_rows = list(
        activity
        .filter(
            action="SERVICE_VIEW"
        )
        .exclude(target_id="")
        .values("target_id")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )

    ids = [
        int(row["target_id"])
        for row in viewed_rows
        if str(row["target_id"]).isdigit()
    ]

    service_map = {
        str(service.pk): service
        for service in Service.objects.filter(
            pk__in=ids
        )
    }

    top_services = []

    for row in viewed_rows:
        service = service_map.get(
            str(row["target_id"])
        )

        if service:
            top_services.append(
                {
                    "service": service,
                    "total": row["total"],
                }
            )


    # =====================================================
    # RECENT SEARCH EVENT TABLE
    # =====================================================

    recent_search_events = (
        search_events
        .order_by("-created_at")[:20]
    )


    # =====================================================
    # RECENT AUDIT ACTIVITY
    # =====================================================

    recent_activity = (
        activity
        .order_by("-created_at")[:20]
    )


    context = {
        "bdes": bdes,
        "selected_bde": selected_bde,

        "selected_start": selected_start,
        "selected_end": selected_end,
        "preset": preset,

        "calendar_weeks": calendar_weeks,
        "calendar_title": first_of_month.strftime(
            "%B %Y"
        ),
        "calendar_month_value": first_of_month.strftime(
            "%Y-%m"
        ),
        "previous_month": previous_month_date.strftime(
            "%Y-%m"
        ),
        "next_month": next_month_date.strftime(
            "%Y-%m"
        ),

        "searches": searches,
        "filters": filters,
        "zero_results": zero_results,
        "successful_searches": successful_searches,
        "unique_queries": unique_queries,

        "service_views": service_views,
        "saves": saves,
        "unsaves": unsaves,
        "current_saved": current_saved,
        "login_count": login_count,
        "active_sessions": active_sessions,

        "chart": chart,
        "top_queries": top_queries,
        "zero_result_queries": zero_result_queries,
        "top_services": top_services,

        "recent_search_events": recent_search_events,
        "recent_activity": recent_activity,
    }

    return render(
        request,
        "dashboard/bde_analytics.html",
        context
    )


# =========================================================
# BDE SEARCH ACTIVITY DAY DRILLDOWN
# =========================================================

from django.contrib.auth.decorators import login_required as _search_activity_login_required


@_search_activity_login_required
def search_activity_detail(request):

    from datetime import timedelta

    from django.shortcuts import render
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    from toolkit.models import SearchEvent


    date_value = (
        request.GET.get("date", "").strip()
    )


    selected_date = parse_date(
        date_value
    )


    if selected_date is None:
        selected_date = timezone.localdate()


    events = (
        SearchEvent.objects
        .filter(
            user=request.user,
            created_at__date=selected_date,
        )
        .select_related(
            "selected_service"
        )
        .order_by(
            "-created_at"
        )
    )


    search_events = events.filter(
        event_type="SEARCH"
    )


    filter_events = events.filter(
        event_type="FILTER"
    )


    matcher_events = events.filter(
        event_type="CLIENT_MATCH"
    )


    suggestion_events = events.filter(
        event_type="SUGGESTION_CLICK"
    )


    total_searches = search_events.count()


    zero_result_searches = (
        search_events
        .filter(
            result_count=0
        )
        .count()
    )


    successful_searches = (
        search_events
        .filter(
            result_count__gt=0
        )
        .count()
    )


    total_results_returned = sum(
        event.result_count or 0
        for event in search_events
    )


    previous_date = (
        selected_date
        - timedelta(days=1)
    )


    next_date = (
        selected_date
        + timedelta(days=1)
    )


    today = timezone.localdate()


    context = {

        "selected_date": selected_date,

        "previous_date": previous_date,

        "next_date": next_date,

        "today": today,

        "events": events,

        "total_events": events.count(),

        "total_searches": total_searches,

        "successful_searches": successful_searches,

        "zero_result_searches": zero_result_searches,

        "filter_count": filter_events.count(),

        "matcher_count": matcher_events.count(),

        "suggestion_count": suggestion_events.count(),

        "total_results_returned": (
            total_results_returned
        ),
    }


    return render(
        request,
        "dashboard/search_activity_detail.html",
        context
    )


# =========================================================
# SEARCH ACTIVITY INVESTIGATION CONSOLE — REDESIGNED
# =========================================================

from django.contrib.auth.decorators import login_required as _activity_console_login_required


@_activity_console_login_required
def search_activity_detail(request):

    from collections import Counter
    from datetime import timedelta

    from django.shortcuts import render
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    from toolkit.models import SearchEvent


    selected_date = parse_date(
        request.GET.get(
            "date",
            ""
        ).strip()
    )


    if selected_date is None:
        selected_date = (
            timezone.localdate()
        )


    events = list(

        SearchEvent.objects
        .filter(
            user=request.user,
            created_at__date=selected_date,
        )
        .select_related(
            "selected_service"
        )
        .order_by(
            "-created_at"
        )

    )


    # =====================================================
    # EVENT COUNTS
    # =====================================================

    type_counts = Counter(
        event.event_type
        for event in events
    )


    total_events = len(
        events
    )


    total_searches = (
        type_counts.get(
            "SEARCH",
            0
        )
    )


    filter_count = (
        type_counts.get(
            "FILTER",
            0
        )
    )


    matcher_count = (
        type_counts.get(
            "CLIENT_MATCH",
            0
        )
    )


    suggestion_count = (
        type_counts.get(
            "SUGGESTION_CLICK",
            0
        )
    )


    successful_searches = sum(
        1
        for event in events

        if (
            event.event_type
            == "SEARCH"

            and (
                event.result_count
                or 0
            ) > 0
        )
    )


    zero_result_searches = sum(
        1
        for event in events

        if (
            event.event_type
            == "SEARCH"

            and (
                event.result_count
                or 0
            ) == 0
        )
    )


    total_results = sum(
        event.result_count
        or 0

        for event in events
    )


    # =====================================================
    # TIMELINE POSITIONING
    # =====================================================

    hour_counts = Counter()


    for event in events:

        local_dt = timezone.localtime(
            event.created_at
        )


        event.console_time = (
            local_dt.strftime(
                "%I:%M %p"
            )
        )


        minutes = (
            local_dt.hour * 60
            + local_dt.minute
        )


        event.timeline_pct = round(
            (
                minutes
                / 1440
            )
            * 100,
            2,
        )


        hour_counts[
            local_dt.hour
        ] += 1


    if hour_counts:

        peak_hour = max(
            hour_counts.items(),
            key=lambda item: (
                item[1],
                item[0],
            ),
        )[0]


        peak_start = (
            f"{peak_hour:02d}:00"
        )


        peak_end = (
            f"{(peak_hour + 1) % 24:02d}:00"
        )


        peak_period = (
            f"{peak_start}–{peak_end}"
        )

    else:

        peak_period = "No activity"


    # =====================================================
    # MOST USED FEATURE
    # =====================================================

    label_map = {

        "SEARCH":
            "Toolkit Search",

        "FILTER":
            "Toolkit Filters",

        "CLIENT_MATCH":
            "Client Matcher",

        "SUGGESTION_CLICK":
            "Search Suggestions",
    }


    if type_counts:

        top_event_type = max(
            type_counts.items(),
            key=lambda item: (
                item[1],
                item[0],
            ),
        )[0]


        most_used_feature = (
            label_map.get(
                top_event_type,
                top_event_type
            )
        )

    else:

        most_used_feature = (
            "No activity"
        )


    previous_date = (
        selected_date
        - timedelta(days=1)
    )


    next_date = (
        selected_date
        + timedelta(days=1)
    )


    context = {

        "selected_date":
            selected_date,

        "previous_date":
            previous_date,

        "next_date":
            next_date,

        "today":
            timezone.localdate(),

        "events":
            events,

        "total_events":
            total_events,

        "total_searches":
            total_searches,

        "successful_searches":
            successful_searches,

        "zero_result_searches":
            zero_result_searches,

        "filter_count":
            filter_count,

        "matcher_count":
            matcher_count,

        "suggestion_count":
            suggestion_count,

        "total_results":
            total_results,

        "peak_period":
            peak_period,

        "most_used_feature":
            most_used_feature,
    }


    return render(
        request,
        "dashboard/search_activity_detail.html",
        context
    )
