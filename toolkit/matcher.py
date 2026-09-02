import re
from decimal import Decimal

from django.utils import timezone


STATE_WILDCARDS = {
    "all india",
    "pan india",
    "all states",
    "any state",
    "india",
    "nationwide",
}

GENERIC_WILDCARDS = {
    "all",
    "any",
    "all businesses",
    "all business types",
    "all stages",
    "all sectors",
    "all industries",
    "all founders",
    "all categories",
}


def normalize(value):
    value = str(value or "").strip().lower()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value


def clean_list(values):
    if not isinstance(values, list):
        return []

    return [
        str(value).strip()
        for value in values
        if str(value).strip()
    ]


def display_values(values):
    cleaned = clean_list(values)

    if not cleaned:
        return "Not specified"

    return ", ".join(cleaned)


def categorical_check(
    client_value,
    service_values,
    label,
    wildcard_values=None,
):
    allowed = clean_list(
        service_values
    )

    if not allowed:
        return None

    if not client_value:
        return {
            "state": "unknown",
            "reason": (
                f"{label} is required by this service "
                "but was not provided."
            ),
        }

    client_normalized = normalize(
        client_value
    )

    allowed_normalized = {
        normalize(value)
        for value in allowed
    }

    wildcards = set(
        GENERIC_WILDCARDS
    )

    if wildcard_values:
        wildcards.update(
            wildcard_values
        )

    if (
        allowed_normalized
        & wildcards
    ):
        return {
            "state": "match",
            "reason": (
                f"{label}: applicable broadly."
            ),
        }

    if client_normalized in allowed_normalized:
        return {
            "state": "match",
            "reason": (
                f"{label} matches: "
                f"{client_value}."
            ),
        }

    return {
        "state": "mismatch",
        "reason": (
            f"{label} mismatch. Toolkit allows: "
            f"{display_values(allowed)}."
        ),
    }


def age_check(
    client_age_months,
    minimum,
    maximum,
):
    if (
        minimum is None
        and maximum is None
    ):
        return None

    if client_age_months is None:
        return {
            "state": "unknown",
            "reason": (
                "Business age criteria exists, "
                "but client business age was not provided."
            ),
        }

    if (
        minimum is not None
        and client_age_months < minimum
    ):
        return {
            "state": "mismatch",
            "reason": (
                "Business is too new. "
                f"Minimum age: {minimum} months."
            ),
        }

    if (
        maximum is not None
        and client_age_months > maximum
    ):
        return {
            "state": "mismatch",
            "reason": (
                "Business exceeds the maximum age. "
                f"Maximum age: {maximum} months."
            ),
        }

    return {
        "state": "match",
        "reason": (
            "Business age is within the "
            "toolkit eligibility range."
        ),
    }


def turnover_check(
    client_turnover,
    minimum,
    maximum,
):
    if (
        minimum is None
        and maximum is None
    ):
        return None

    if client_turnover is None:
        return {
            "state": "unknown",
            "reason": (
                "Turnover criteria exists, "
                "but client turnover was not provided."
            ),
        }

    if (
        minimum is not None
        and client_turnover < minimum
    ):
        return {
            "state": "mismatch",
            "reason": (
                "Client turnover is below the "
                f"minimum requirement of ₹{minimum:,.0f}."
            ),
        }

    if (
        maximum is not None
        and client_turnover > maximum
    ):
        return {
            "state": "mismatch",
            "reason": (
                "Client turnover exceeds the "
                f"maximum limit of ₹{maximum:,.0f}."
            ),
        }

    return {
        "state": "match",
        "reason": (
            "Annual turnover is within the "
            "toolkit eligibility range."
        ),
    }


SEARCH_STOPWORDS = {
    "related",
    "relating",
    "for",
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "or",
    "client",
    "company",
    "business",
    "scheme",
    "schemes",
    "service",
    "services",
    "looking",
    "need",
    "needs",
}


def keyword_matches(
    service,
    keyword,
):
    query = normalize(
        keyword
    )

    if not query:
        return True

    searchable_values = [
        service.service_id,
        service.title,
        service.domain.name,
        service.category.name,
        service.bde_summary,
        service.overview,
        service.benefits,
        service.eligibility_summary,
        service.restrictions,
        service.important_notes,
        service.funding_type,
        service.subsidy_details,
    ]

    searchable_values.extend(
        clean_list(
            service.industries
        )
    )

    searchable_values.extend(
        clean_list(
            service.business_types
        )
    )

    searchable_values.extend(
        clean_list(
            service.business_stages
        )
    )

    searchable_text = " ".join(
        normalize(value)
        for value in searchable_values
        if value
    )


    # Exact phrase is strongest.
    if query in searchable_text:
        return True


    # Natural queries such as
    # "technology related schemes"
    # become meaningful terms such as
    # ["technology"].
    tokens = re.findall(
        r"[a-z0-9]+",
        query
    )

    meaningful_tokens = [
        token
        for token in tokens
        if (
            len(token) > 2
            and token
            not in SEARCH_STOPWORDS
        )
    ]


    if not meaningful_tokens:
        meaningful_tokens = [
            token
            for token in tokens
            if len(token) > 2
        ]


    if not meaningful_tokens:
        return False


    # Deterministic matching:
    # every meaningful term must exist
    # somewhere in the actual Toolkit record.
    return all(
        token in searchable_text
        for token in meaningful_tokens
    )


def evaluate_service(
    service,
    profile,
):
    checks = []

    categorical_fields = [
        (
            profile.get(
                "business_type"
            ),
            service.business_types,
            "Business type",
            None,
        ),
        (
            profile.get(
                "business_stage"
            ),
            service.business_stages,
            "Business stage",
            None,
        ),
        (
            profile.get(
                "industry"
            ),
            service.industries,
            "Industry",
            None,
        ),
        (
            profile.get(
                "state"
            ),
            service.applicable_states,
            "State",
            STATE_WILDCARDS,
        ),
        (
            profile.get(
                "founder_category"
            ),
            service.founder_categories,
            "Founder category",
            None,
        ),
    ]

    for (
        client_value,
        service_values,
        label,
        wildcards,
    ) in categorical_fields:

        result = categorical_check(
            client_value,
            service_values,
            label,
            wildcard_values=wildcards,
        )

        if result:
            checks.append(
                result
            )


    age_result = age_check(
        profile.get(
            "business_age_months"
        ),
        service.min_business_age_months,
        service.max_business_age_months,
    )

    if age_result:
        checks.append(
            age_result
        )


    turnover_result = turnover_check(
        profile.get(
            "annual_turnover"
        ),
        service.min_turnover,
        service.max_turnover,
    )

    if turnover_result:
        checks.append(
            turnover_result
        )


    # Current toolkit deadline is treated as an
    # explicit eligibility warning.
    if (
        service.application_deadline
        and (
            service.application_deadline
            < timezone.localdate()
        )
    ):
        checks.append(
            {
                "state": "mismatch",
                "reason": (
                    "Application deadline recorded in "
                    "the toolkit has already passed."
                ),
            }
        )


    matches = [
        item
        for item in checks
        if item["state"] == "match"
    ]

    mismatches = [
        item
        for item in checks
        if item["state"] == "mismatch"
    ]

    unknowns = [
        item
        for item in checks
        if item["state"] == "unknown"
    ]


    if mismatches:
        classification = (
            "NOT_ELIGIBLE"
        )

    elif matches and not unknowns:
        classification = (
            "HIGH"
        )

    else:
        classification = (
            "POSSIBLE"
        )


    return {
        "service": service,

        "classification": (
            classification
        ),

        "matches": matches,
        "mismatches": mismatches,
        "unknowns": unknowns,

        "matched_count": len(
            matches
        ),

        "criteria_count": len(
            checks
        ),

        "unknown_count": len(
            unknowns
        ),
    }


def build_matches(
    services,
    profile,
):
    """
    CLIENT_MATCHER_INTELLIGENT_SEARCH_V2

    Structured eligibility remains authoritative.

    need_query now uses the same intelligent search surfaces
    as the Business Toolkit:
        - core Service text
        - sectors
        - BDE business knowledge
        - English/Hinglish natural-language understanding
        - numeric-aware relevance ranking

    evaluate_service() is intentionally unchanged.
    """

    keyword = profile.get(
        "need_query",
        ""
    )


    requested_kinds = set(
        profile.get(
            "service_kinds",
            []
        )
    )


    high = []
    possible = []
    not_eligible = []


    intelligent_ids = None
    relevance_scores = {}


    # ========================================================
    # INTELLIGENT FREE-TEXT NEED SEARCH
    # ========================================================

    if keyword:

        # Local imports intentionally avoid coupling
        # matcher.py to views.py during module initialization.
        from .views import (
            business_knowledge_match_ids,
            natural_language_match_ids,
            natural_language_rank_map,
            search_relevance_sort_key,
            search_text_filter,
        )

        from .pitching import (
            sector_match_ids,
        )


        # The normal Client Matcher receives a QuerySet.
        # Preserve old keyword matching as a safe fallback
        # if another caller ever supplies a plain iterable.
        if hasattr(
            services,
            "filter",
        ):

            core_ids = set(
                services
                .filter(
                    search_text_filter(
                        keyword
                    )
                )
                .distinct()
                .values_list(
                    "pk",
                    flat=True,
                )
            )


            sector_ids = set(
                sector_match_ids(
                    services,
                    keyword,
                )
            )


            knowledge_ids = set(
                business_knowledge_match_ids(
                    keyword
                )
            )


            natural_ids = set(
                natural_language_match_ids(
                    services,
                    keyword,
                )
            )


            intelligent_ids = (
                core_ids
                | sector_ids
                | knowledge_ids
                | natural_ids
            )


            relevance_scores = (
                natural_language_rank_map(
                    services,
                    keyword,
                )
            )


        else:

            search_relevance_sort_key = None


    else:

        search_relevance_sort_key = None


    # ========================================================
    # EXISTING STRUCTURED ELIGIBILITY EVALUATION
    # ========================================================

    for service in services:

        if (
            requested_kinds
            and (
                service.service_kind
                not in requested_kinds
            )
        ):

            continue


        if keyword:

            if intelligent_ids is not None:

                if (
                    service.pk
                    not in intelligent_ids
                ):

                    continue


            elif not keyword_matches(
                service,
                keyword,
            ):

                continue


        result = evaluate_service(
            service,
            profile,
        )


        # ----------------------------------------------------
        # INTERNAL SEARCH RELEVANCE
        #
        # Never displayed as confidence or eligibility.
        # It is only a tie-breaker after structured checks.
        # ----------------------------------------------------

        relevance = 0


        if (
            keyword
            and search_relevance_sort_key
            is not None
        ):

            ranking_key = (
                search_relevance_sort_key(
                    service,
                    relevance_scores,
                    keyword,
                )
            )


            # search_relevance_sort_key returns
            # negative score first because normal Search
            # sorts ascending.
            relevance = max(
                0,
                -int(
                    ranking_key[0]
                ),
            )


        result[
            "_search_relevance"
        ] = relevance


        if (
            result["classification"]
            == "HIGH"
        ):

            high.append(
                result
            )


        elif (
            result["classification"]
            == "POSSIBLE"
        ):

            possible.append(
                result
            )


        else:

            not_eligible.append(
                result
            )


    # ========================================================
    # RANKING
    #
    # Eligibility remains ahead of search relevance:
    #
    # 1. more structured criteria matched
    # 2. fewer unknown eligibility facts
    # 3. stronger client-need relevance
    # 4. existing Service priority
    #
    # HIGH / POSSIBLE / NOT_ELIGIBLE buckets remain separate.
    # ========================================================

    priority_rank = {
        "CRITICAL": 4,
        "HIGH": 3,
        "NORMAL": 2,
        "LOW": 1,
    }


    def eligible_sort_key(
        item
    ):

        return (
            -item[
                "matched_count"
            ],

            item[
                "unknown_count"
            ],

            -item.get(
                "_search_relevance",
                0,
            ),

            -priority_rank.get(
                item[
                    "service"
                ].priority,
                0,
            ),

            str(
                item[
                    "service"
                ].title
            ).casefold(),
        )


    def ineligible_sort_key(
        item
    ):

        return (
            len(
                item[
                    "mismatches"
                ]
            ),

            -item[
                "matched_count"
            ],

            -item.get(
                "_search_relevance",
                0,
            ),

            str(
                item[
                    "service"
                ].title
            ).casefold(),
        )


    high.sort(
        key=eligible_sort_key,
    )


    possible.sort(
        key=eligible_sort_key,
    )


    not_eligible.sort(
        key=ineligible_sort_key,
    )


    return {
        "high": high[:50],

        "possible": (
            possible[:50]
        ),

        "not_eligible": (
            not_eligible[:50]
        ),

        "high_count": len(
            high
        ),

        "possible_count": len(
            possible
        ),

        "not_eligible_count": len(
            not_eligible
        ),
    }

