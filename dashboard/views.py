from toolkit.visibility import visible_service_statuses
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
        status__in=visible_service_statuses(request.user)
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
                    services__status__in=visible_service_statuses(request.user)
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
    from accounts.portal_access import is_admin_user

    return is_admin_user(user)


@login_required
def admin_overview(request):
    if not can_access_admin_center(request.user):
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "requested_area": "Admin Center",
            },
            status=403,
        )

    employees = User.objects.all()
    services = Service.objects.all()

    context = {
        "total_employees": employees.count(),

        "active_employees": employees.filter(
            is_account_active=True
        ).count(),

        "total_services": services.count(),

        "published_services": services.filter(
            status__in=visible_service_statuses(request.user)
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
    from accounts.portal_access import is_admin_user

    return is_admin_user(user)


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



# ============================================================
# BHARATNXT WAVE HOME DASHBOARD V2
# ============================================================

from django.contrib.auth.decorators import login_required as _home_v2_login_required


@_home_v2_login_required
def home_v2(request):
    # BNW_ROLE_PORTAL_ROUTING_V1
    from accounts.portal_access import is_admin_user as _is_admin_user
    from django.shortcuts import redirect as _portal_redirect

    if _is_admin_user(request.user):
        return _portal_redirect(
            "dashboard:admin_overview"
        )

    from collections import defaultdict
    from datetime import timedelta

    from django.db.models import Count
    from django.urls import NoReverseMatch, reverse
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    from accounts.models import ActivityLog
    from toolkit.models import SavedService, SearchEvent, Service
    from toolkit.pitching import (
        apply_pitch_states,
        closing_soon_queryset,
    )

    today = timezone.localdate()

    preset = request.GET.get("preset", "").strip()
    requested_start = parse_date(request.GET.get("start", ""))
    requested_end = parse_date(request.GET.get("end", ""))

    if requested_start and requested_end:
        selected_start = min(requested_start, requested_end)
        selected_end = max(requested_start, requested_end)
    elif preset == "today":
        selected_start = today
        selected_end = today
    elif preset == "30d":
        selected_start = today - timedelta(days=29)
        selected_end = today
    else:
        selected_start = today - timedelta(days=6)
        selected_end = today

    if selected_end > today:
        selected_end = today

    max_start = selected_end - timedelta(days=89)

    if selected_start < max_start:
        selected_start = max_start

    events = SearchEvent.objects.filter(
        user=request.user,
        created_at__date__range=(
            selected_start,
            selected_end,
        ),
    )

    activity_logs = ActivityLog.objects.filter(
        user=request.user,
        created_at__date__range=(
            selected_start,
            selected_end,
        ),
    )

    search_count = events.filter(
        event_type="SEARCH"
    ).count()

    client_check_count = events.filter(
        event_type="CLIENT_MATCH"
    ).count()

    filter_count = events.filter(
        event_type="FILTER"
    ).count()

    zero_result_count = events.filter(
        event_type="SEARCH",
        result_count=0,
    ).count()

    service_view_count = activity_logs.filter(
        action="SERVICE_VIEW"
    ).count()

    saved_service_count = SavedService.objects.filter(
        user=request.user
    ).count()

    save_actions = {
        "SERVICE_SAVE",
        "SERVICE_UNSAVE",
        "COLLECTION_CREATE",
        "COLLECTION_RENAME",
        "COLLECTION_DELETE",
        "COLLECTION_ADD_SERVICE",
        "COLLECTION_REMOVE_SERVICE",
    }

    flyer_actions = {
        "SERVICE_FLYER_PREVIEW",
        "SERVICE_FLYER_DOWNLOAD",
    }

    session_actions = {
        "LOGIN",
        "LOGOUT",
    }

    saved_activity_count = activity_logs.filter(
        action__in=save_actions
    ).count()

    flyer_activity_count = activity_logs.filter(
        action__in=flyer_actions
    ).count()

    external_link_count = activity_logs.filter(
        action="EXTERNAL_LINK_OPEN"
    ).count()

    session_activity_count = activity_logs.filter(
        action__in=session_actions
    ).count()

    canonical_log_actions = {
        "SEARCH",
        "FILTER",
        "CLIENT_MATCH",
    }

    action_group_map = {
        "SERVICE_VIEW": "views",

        "SERVICE_SAVE": "saved",
        "SERVICE_UNSAVE": "saved",
        "COLLECTION_CREATE": "saved",
        "COLLECTION_RENAME": "saved",
        "COLLECTION_DELETE": "saved",
        "COLLECTION_ADD_SERVICE": "saved",
        "COLLECTION_REMOVE_SERVICE": "saved",

        "SERVICE_FLYER_PREVIEW": "flyer",
        "SERVICE_FLYER_DOWNLOAD": "flyer",

        "EXTERNAL_LINK_OPEN": "external",

        "LOGIN": "sessions",
        "LOGOUT": "sessions",
    }

    known_log_actions = (
        canonical_log_actions
        | set(action_group_map)
    )

    other_activity_count = activity_logs.exclude(
        action__in=known_log_actions
    ).count()

    activity_breakdown = [
        {
            "key": "search",
            "label": "Toolkit Searches",
            "description": "Completed scheme and service searches",
            "color": "#1769ff",
            "count": search_count,
        },
        {
            "key": "client",
            "label": "Client Checks",
            "description": "Service suitability checks for clients",
            "color": "#d99a16",
            "count": client_check_count,
        },
        {
            "key": "views",
            "label": "Service Views",
            "description": "Quick Views and full service pages",
            "color": "#7c3aed",
            "count": service_view_count,
        },
        {
            "key": "filters",
            "label": "Filters Applied",
            "description": "Service Library filtering activity",
            "color": "#06b6d4",
            "count": filter_count,
        },
        {
            "key": "saved",
            "label": "Saved & Collections",
            "description": "Saving, organising and removing services",
            "color": "#10b981",
            "count": saved_activity_count,
        },
        {
            "key": "flyer",
            "label": "Flyer Activity",
            "description": "Official flyer previews and downloads",
            "color": "#f97316",
            "count": flyer_activity_count,
        },
        {
            "key": "external",
            "label": "Official Links Opened",
            "description": "Scheme portals and official sources opened",
            "color": "#ec4899",
            "count": external_link_count,
        },
        {
            "key": "sessions",
            "label": "Login Activity",
            "description": "Recorded login and logout actions",
            "color": "#64748b",
            "count": session_activity_count,
        },
        {
            "key": "other",
            "label": "Other Recorded Actions",
            "description": "Imports, uploads and administrative activity",
            "color": "#94a3b8",
            "count": other_activity_count,
        },
    ]

    total_activity_count = sum(
        item["count"]
        for item in activity_breakdown
    )

    max_breakdown_count = max(
        (
            item["count"]
            for item in activity_breakdown
        ),
        default=0,
    ) or 1

    for item in activity_breakdown:
        exact_percentage = (
            (item["count"] / total_activity_count) * 100
            if total_activity_count
            else 0
        )

        item["percentage"] = round(exact_percentage)
        item["relative_width"] = (
            max(
                4,
                round(
                    (item["count"] / max_breakdown_count) * 100,
                    2,
                ),
            )
            if item["count"]
            else 0
        )

    activity_overview = [
        {
            "key": "discover",
            "label": "Search & Filter",
            "description": "Services searched and Library filters applied",
            "color": "#2563eb",
            "count": search_count + filter_count,
        },
        {
            "key": "research",
            "label": "Service Research",
            "description": "Service pages, flyers and official links reviewed",
            "color": "#7c3aed",
            "count": (
                service_view_count
                + flyer_activity_count
                + external_link_count
            ),
        },
        {
            "key": "client",
            "label": "Find for Client",
            "description": "Times suitable services were checked for a client",
            "color": "#d99a16",
            "count": client_check_count,
        },
        {
            "key": "saved",
            "label": "Saved & Collections",
            "description": "Services saved, organised or removed",
            "color": "#10b981",
            "count": saved_activity_count,
        },
        {
            "key": "system",
            "label": "Sessions & Other",
            "description": "Login, logout and other recorded actions",
            "color": "#64748b",
            "count": session_activity_count + other_activity_count,
        },
    ]

    overview_offset = 0.0

    for item in activity_overview:
        exact_percentage = (
            (item["count"] / total_activity_count) * 100
            if total_activity_count
            else 0
        )

        item["percentage"] = round(exact_percentage)
        item["dasharray"] = (
            f"{exact_percentage:.4f} "
            f"{100 - exact_percentage:.4f}"
        )
        item["dashoffset"] = f"{-overview_offset:.4f}"
        overview_offset += exact_percentage

    daily_lookup = defaultdict(
        lambda: defaultdict(int)
    )

    event_group_map = {
        "SEARCH": "search",
        "CLIENT_MATCH": "client",
        "FILTER": "filters",
    }

    for row in (
        events
        .filter(event_type__in=event_group_map)
        .values(
            "created_at__date",
            "event_type",
        )
        .annotate(total=Count("id"))
    ):
        group_key = event_group_map[row["event_type"]]
        daily_lookup[
            row["created_at__date"]
        ][group_key] += row["total"]

    for row in (
        activity_logs
        .values(
            "created_at__date",
            "action",
        )
        .annotate(total=Count("id"))
    ):
        action = row["action"]

        if action in canonical_log_actions:
            continue

        group_key = action_group_map.get(
            action,
            "other",
        )

        daily_lookup[
            row["created_at__date"]
        ][group_key] += row["total"]

    daily_activity = []
    day = selected_start

    while day <= selected_end:
        segments = []
        total = 0

        for item in activity_breakdown:
            count = daily_lookup[day][item["key"]]
            total += count

            segments.append(
                {
                    "key": item["key"],
                    "label": item["label"],
                    "color": item["color"],
                    "count": count,
                }
            )

        daily_activity.append(
            {
                "date": day,
                "label": day.strftime("%d %b"),
                "total_count": total,
                "segments": segments,
            }
        )

        day += timedelta(days=1)

    max_daily_total = max(
        (
            row["total_count"]
            for row in daily_activity
        ),
        default=0,
    )

    max_daily_total = max(max_daily_total, 1)

    mid_daily_total = round(max_daily_total / 2)

    for row in daily_activity:
        row["height"] = (
            max(
                6,
                round(
                    (row["total_count"] / max_daily_total) * 100,
                    2,
                ),
            )
            if row["total_count"]
            else 0
        )

        for segment in row["segments"]:
            segment["height"] = round(
                (
                    segment["count"]
                    / max_daily_total
                )
                * 100,
                2,
            )

    top_queries = list(
        events
        .filter(event_type="SEARCH")
        .exclude(query="")
        .values("query")
        .annotate(total=Count("id"))
        .order_by("-total", "query")[:6]
    )

    zero_queries = list(
        events
        .filter(
            event_type="SEARCH",
            result_count=0,
        )
        .exclude(query="")
        .values("query")
        .annotate(total=Count("id"))
        .order_by("-total", "query")[:6]
    )

    breakdown_by_key = {
        item["key"]: item
        for item in activity_breakdown
    }

    def dashboard_day_url(created_at):
        local_day = timezone.localtime(
            created_at
        ).date()

        return (
            f"?start={local_day.isoformat()}"
            f"&end={local_day.isoformat()}"
            "#recent-toolkit-activity"
        )

    recent_event_rows = list(
        events
        .filter(
            event_type__in=[
                "SEARCH",
                "CLIENT_MATCH",
                "FILTER",
            ]
        )
        .order_by("-created_at")[:30]
    )

    recent_log_rows = list(
        activity_logs
        .exclude(action__in=canonical_log_actions)
        .order_by("-created_at")[:40]
    )

    service_target_ids = set()

    for activity in recent_log_rows:
        if (
            str(activity.target_type).lower() == "service"
            and str(activity.target_id).isdigit()
        ):
            service_target_ids.add(int(activity.target_id))

    services_by_pk = Service.objects.in_bulk(
        service_target_ids
    )

    def saved_services_url(fallback):
        try:
            return reverse("toolkit:saved_services")
        except NoReverseMatch:
            return fallback

    def service_activity_url(activity):
        fallback = dashboard_day_url(activity.created_at)

        if action_group_map.get(activity.action) == "saved":
            return saved_services_url(fallback)

        if (
            str(activity.target_type).lower() != "service"
            or not str(activity.target_id).isdigit()
        ):
            return fallback

        service = services_by_pk.get(
            int(activity.target_id)
        )

        if service is None:
            return fallback

        get_absolute_url = getattr(
            service,
            "get_absolute_url",
            None,
        )

        if callable(get_absolute_url):
            try:
                url = get_absolute_url()
                if url:
                    return url
            except (NoReverseMatch, TypeError, AttributeError):
                pass

        identifiers = [
            getattr(service, "slug", None),
            service.pk,
        ]

        for identifier in identifiers:
            if identifier in (None, ""):
                continue

            try:
                return reverse(
                    "toolkit:service_detail",
                    args=[identifier],
                )
            except NoReverseMatch:
                continue

        return fallback

    recent_activity = []

    for event in recent_event_rows:
        group_key = event_group_map[event.event_type]
        group = breakdown_by_key[group_key]

        if event.event_type == "SEARCH":
            description = (
                f'Searched for "{event.query}"'
                if event.query
                else "Completed a Toolkit search"
            )
        elif event.event_type == "CLIENT_MATCH":
            description = (
                "Checked suitable services for a client"
            )
        else:
            description = "Applied Service Library filters"

        result_count = event.result_count or 0

        recent_activity.append(
            {
                "created_at": event.created_at,
                "group_key": group_key,
                "label": group["label"],
                "color": group["color"],
                "description": description,
                "detail": (
                    f"{result_count} result"
                    if result_count == 1
                    else f"{result_count} results"
                ),
                "view_url": dashboard_day_url(
                    event.created_at
                ),
            }
        )

    for activity in recent_log_rows:
        group_key = action_group_map.get(
            activity.action,
            "other",
        )

        group = breakdown_by_key[group_key]

        recent_activity.append(
            {
                "created_at": activity.created_at,
                "group_key": group_key,
                "label": group["label"],
                "color": group["color"],
                "description": activity.description,
                "detail": activity.action.replace(
                    "_",
                    " ",
                ).title(),
                "view_url": service_activity_url(
                    activity
                ),
            }
        )

    recent_activity = sorted(
        recent_activity,
        key=lambda item: item["created_at"],
        reverse=True,
    )[:12]

    closing_soon_services = list(
        closing_soon_queryset(
            Service.objects.select_related(
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

    apply_pitch_states(closing_soon_services)

    context = {
        "selected_start": selected_start,
        "selected_end": selected_end,
        "today": today,

        "search_count": search_count,
        "client_check_count": client_check_count,
        "service_view_count": service_view_count,
        "saved_service_count": saved_service_count,
        "zero_result_count": zero_result_count,
        "filter_count": filter_count,

        "activity_breakdown": activity_breakdown,
        "activity_overview": activity_overview,
        "total_activity_count": total_activity_count,
        "daily_activity": daily_activity,
        "max_daily_total": max_daily_total,
        "mid_daily_total": mid_daily_total,

        "top_queries": top_queries,
        "zero_queries": zero_queries,
        "recent_activity": recent_activity,
        "closing_soon_services": closing_soon_services,
    }

    return render(
        request,
        "dashboard/home.html",
        context,
    )

