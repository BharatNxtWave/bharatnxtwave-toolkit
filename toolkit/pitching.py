import re
from collections import Counter
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone


VISIBLE_STATUSES = [
    "APPROVED",
    "PUBLISHED",
    "EXPIRING",
]


SEARCH_STOPWORDS = {
    "scheme",
    "schemes",
    "service",
    "services",
    "sector",
    "related",
    "for",
    "the",
    "and",
    "business",
    "company",
    "client",
}


def normalize(value):
    value = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", value)


def meaningful_terms(value):
    tokens = re.findall(
        r"[a-z0-9]+",
        normalize(value)
    )

    terms = [
        token
        for token in tokens
        if (
            len(token) > 2
            and token not in SEARCH_STOPWORDS
        )
    ]

    return terms or [
        token
        for token in tokens
        if len(token) > 2
    ]


def pitchable_queryset(queryset, today=None):
    today = today or timezone.localdate()

    return queryset.filter(
        status__in=VISIBLE_STATUSES
    ).filter(
        Q(effective_from__isnull=True)
        | Q(effective_from__lte=today)
    ).filter(
        Q(pitch_until__isnull=True)
        | Q(pitch_until__gte=today)
    ).filter(
        Q(application_deadline__isnull=True)
        | Q(application_deadline__gte=today)
    )


def closing_soon_queryset(queryset, days=30, today=None):
    today = today or timezone.localdate()
    end = today + timedelta(days=days)

    queryset = pitchable_queryset(
        queryset,
        today=today
    )

    return queryset.filter(
        Q(
            pitch_until__gte=today,
            pitch_until__lte=end,
        )
        |
        Q(
            pitch_until__isnull=True,
            application_deadline__gte=today,
            application_deadline__lte=end,
        )
    )


def pitch_state(service, today=None):
    today = today or timezone.localdate()

    if (
        service.effective_from
        and service.effective_from > today
    ):
        return {
            "code": "UPCOMING",
            "label": "Upcoming",
            "days_remaining": None,
            "end_date": None,
            "end_label": "Effective From",
            "effective_from": service.effective_from,
            "pitchable": False,
        }

    end_candidates = []

    if service.pitch_until:
        end_candidates.append(
            (
                service.pitch_until,
                "Pitch Until"
            )
        )

    if service.application_deadline:
        end_candidates.append(
            (
                service.application_deadline,
                "Application Deadline"
            )
        )

    if not end_candidates:
        return {
            "code": "ACTIVE",
            "label": "Pitch Now",
            "days_remaining": None,
            "end_date": None,
            "end_label": "No Deadline",
            "effective_from": service.effective_from,
            "pitchable": True,
        }

    end_date, end_label = min(
        end_candidates,
        key=lambda item: item[0]
    )

    days_remaining = (
        end_date - today
    ).days

    if days_remaining < 0:
        return {
            "code": "CLOSED",
            "label": "Pitch Window Closed",
            "days_remaining": days_remaining,
            "end_date": end_date,
            "end_label": end_label,
            "effective_from": service.effective_from,
            "pitchable": False,
        }

    if days_remaining <= 7:
        code = "URGENT"
        label = "Closing Very Soon"

    elif days_remaining <= 30:
        code = "CLOSING"
        label = "Closing Soon"

    else:
        code = "ACTIVE"
        label = "Pitch Now"

    return {
        "code": code,
        "label": label,
        "days_remaining": days_remaining,
        "end_date": end_date,
        "end_label": end_label,
        "effective_from": service.effective_from,
        "pitchable": True,
    }


def apply_pitch_state(service):
    state = pitch_state(service)

    service.pitch_state_code = state["code"]
    service.pitch_state_label = state["label"]
    service.pitch_days_remaining = state["days_remaining"]
    service.pitch_end_date = state["end_date"]
    service.pitch_end_label = state["end_label"]
    service.is_pitchable_now = state["pitchable"]

    return service


def apply_pitch_states(services):
    for service in services:
        apply_pitch_state(service)

    return services


def sector_matches(sectors, search_value):
    if not isinstance(sectors, list):
        return False

    terms = meaningful_terms(search_value)

    if not terms:
        return False

    searchable = " ".join(
        normalize(item)
        for item in sectors
        if item
    )

    return all(
        term in searchable
        for term in terms
    )


def sector_match_ids(queryset, search_value):
    terms = meaningful_terms(search_value)

    if not terms:
        return []

    matched = []

    for service in queryset.select_related(None).only(
        "id",
        "industries"
    ):
        if sector_matches(
            service.industries,
            search_value
        ):
            matched.append(service.pk)

    return matched


def available_sectors(queryset):
    counts = Counter()

    ignored = {
        "all",
        "all india",
        "all industries",
        "all sectors",
        "any",
        "any industry",
    }

    for industries in queryset.values_list(
        "industries",
        flat=True
    ):
        if not isinstance(industries, list):
            continue

        seen = set()

        for value in industries:
            name = str(value or "").strip()

            if not name:
                continue

            key = normalize(name)

            if (
                key in ignored
                or key in seen
            ):
                continue

            seen.add(key)
            counts[name] += 1

    return [
        {
            "name": name,
            "count": count,
        }
        for name, count
        in sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0].lower()
            )
        )
    ]
