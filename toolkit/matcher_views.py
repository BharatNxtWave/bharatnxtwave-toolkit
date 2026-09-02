from toolkit.visibility import visible_service_statuses
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.activity import log_activity

from .matcher import build_matches
from .matcher_forms import ClientMatcherForm
from .models import SavedService, SearchEvent, Service
from .pitching import pitchable_queryset


VISIBLE_STATUSES = [
    "APPROVED",
    "PUBLISHED",
    "EXPIRING",
]


TURNOVER_MULTIPLIERS = {
    "RUPEES": Decimal("1"),
    "LAKH": Decimal("100000"),
    "CRORE": Decimal("10000000"),
}


@login_required
def client_matcher(request):
    results = None
    submitted = False

    if request.method == "POST":

        form = ClientMatcherForm(
            request.POST
        )

        if form.is_valid():
            submitted = True

            cleaned = form.cleaned_data

            age_years = cleaned.get(
                "business_age_years"
            )

            business_age_months = None

            if age_years is not None:
                business_age_months = int(
                    age_years * Decimal("12")
                )


            turnover_amount = cleaned.get(
                "turnover_amount"
            )

            annual_turnover = None

            if turnover_amount is not None:

                turnover_unit = cleaned.get(
                    "turnover_unit"
                ) or "LAKH"

                multiplier = (
                    TURNOVER_MULTIPLIERS.get(
                        turnover_unit,
                        Decimal("1")
                    )
                )

                annual_turnover = (
                    turnover_amount
                    * multiplier
                )


            profile = {
                "need_query": (
                    cleaned.get(
                        "need_query",
                        ""
                    )
                ),

                "service_kinds": (
                    cleaned.get(
                        "service_kinds",
                        []
                    )
                ),

                "business_type": (
                    cleaned.get(
                        "business_type",
                        ""
                    )
                ),

                "business_stage": (
                    cleaned.get(
                        "business_stage",
                        ""
                    )
                ),

                "industry": (
                    cleaned.get(
                        "industry",
                        ""
                    )
                ),

                "state": (
                    cleaned.get(
                        "state",
                        ""
                    )
                ),

                "founder_category": (
                    cleaned.get(
                        "founder_category",
                        ""
                    )
                ),

                "business_age_months": (
                    business_age_months
                ),

                "annual_turnover": (
                    annual_turnover
                ),
            }


            services = pitchable_queryset(
                Service.objects
                .select_related(
                    "domain",
                    "category",
                    "verified_by",
                )
            )


            results = build_matches(
                services,
                profile,
            )


            # Privacy-safe analytics only.
            # Client profile values are deliberately
            # NOT saved to SearchEvent.
            criteria_count = sum(
                1
                for key in (
                    "business_type",
                    "business_stage",
                    "industry",
                    "state",
                    "founder_category",
                    "business_age_months",
                    "annual_turnover",
                )
                if profile.get(key)
                not in (
                    "",
                    None,
                    [],
                )
            )

            relevant_count = (
                results["high_count"]
                + results[
                    "possible_count"
                ]
            )

            SearchEvent.objects.create(
                user=request.user,

                event_type="CLIENT_MATCH",

                query="",

                filters={
                    "criteria_count": (
                        criteria_count
                    ),

                    "has_keyword": bool(
                        profile[
                            "need_query"
                        ]
                    ),

                    "requested_kind_count": (
                        len(
                            profile[
                                "service_kinds"
                            ]
                        )
                    ),

                    "high_match_count": (
                        results[
                            "high_count"
                        ]
                    ),

                    "possible_match_count": (
                        results[
                            "possible_count"
                        ]
                    ),

                    "not_eligible_count": (
                        results[
                            "not_eligible_count"
                        ]
                    ),
                },

                result_count=(
                    relevant_count
                ),
            )

            log_activity(
                request,
                "CLIENT_MATCH",
                "Checked suitable services for a client.",
                metadata={
                    "criteria_count": criteria_count,
                    "requested_kind_count": len(
                        profile["service_kinds"]
                    ),
                    "high_match_count": results["high_count"],
                    "possible_match_count": (
                        results["possible_count"]
                    ),
                    "result_count": relevant_count,
                },
            )

    else:
        form = ClientMatcherForm()


    saved_service_ids = set(
        SavedService.objects
        .filter(user=request.user)
        .values_list(
            "service_id",
            flat=True
        )
    )

    return render(
        request,
        "toolkit/client_matcher.html",
        {
            "form": form,
            "results": results,
            "submitted": submitted,
            "saved_service_ids": saved_service_ids,
        }
    )
