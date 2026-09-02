# BNW_CORE_ACTIVITY_TRACKING_V1
from toolkit.visibility import visible_service_statuses
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
from django.views.decorators.http import require_GET, require_POST

from accounts.activity import log_activity

from .models import (
    Category,
    SavedCollection,
    SavedCollectionItem,
    SavedService,
    SearchEvent,
    Service,
    ServiceDomain,
    ServiceSource,
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


SOURCE_PRIORITY = {
    "APPLICATION": 0,
    "OFFICIAL_PORTAL": 1,
    "REFERENCE": 2,
    "FLYER": 3,
    "OTHER": 4,
}

SOURCE_LABELS = {
    "APPLICATION": "Apply / Open Portal",
    "OFFICIAL_PORTAL": "Official Scheme Page",
    "REFERENCE": "Reference",
    "FLYER": "Guidelines / Flyer",
    "OTHER": "External Link",
}


def visible_services():
    """
    Services that are currently pitchable according to the pitch-window engine.
    Kept for pitch-window-specific workflows.
    """
    return pitchable_queryset(
        Service.objects.select_related(
            "domain",
            "category",
            "verified_by",
        )
    )


def all_bde_services():
    """
    Complete BDE catalog.

    Published/approved statuses are visible even when a pitch-window warning
    exists. The UI shows the pitch state instead of silently hiding the record.
    """
    return (
        Service.objects
        .select_related(
            "domain",
            "category",
            "verified_by",
        )
        .prefetch_related(
            "sources",
            "classifications",
            "eligibility_rules",
            "document_requirements",
            "process_steps",
        )
        .filter(
            status__in=VISIBLE_STATUSES
        )
    )



def business_knowledge_match_ids(query):
    """
    Return Service IDs matched through BDE-visible
    supporting business knowledge.

    Raw imports, hashes, audit data and technical metadata
    are deliberately excluded.
    """

    from django.apps import apps

    from django.db import (
        models as django_models,
    )

    from django.db.models import (
        Q as KnowledgeQ,
    )


    query = str(
        query or ""
    ).strip()


    if not query:

        return set()


    # Explicit allow-list.
    # Technical models such as ImportBatch, ImportRow,
    # ImportChange and audit/security models are absent.
    business_models = (
        "ServiceContentSection",
        "ServiceCommercial",
        "ServiceSource",
        "KnowledgeSection",
        "EligibilityRule",
        "DocumentRequirement",
        "ProcessStep",
        "ReferenceItem",
        "CommunicationTemplate",
    )


    blocked_fields = {
        "visibility",
        "status",
        "section_type",
        "content_type",
        "kind",
        "source_kind",
        "source_type",
        "source_reference",
        "source_sheet",
        "source_row_number",
        "row_hash",
        "raw_data",
        "metadata",
        "before_snapshot",
        "after_snapshot",
        "object_model",
        "object_pk",
        "engine_version",
        "ip_address",
        "user_agent",
    }


    blocked_fragments = (
        "internal",
        "technical",
        "audit",
        "hash",
        "import_",
        "created_by",
        "updated_by",
    )


    service_ids = set()


    for model_name in business_models:

        try:

            Model = apps.get_model(
                "toolkit",
                model_name,
            )

        except LookupError:

            continue


        # ----------------------------------------------------
        # REQUIRE DIRECT SERVICE RELATION
        # ----------------------------------------------------

        service_field = None


        for field in Model._meta.fields:

            remote = getattr(
                field,
                "remote_field",
                None,
            )

            remote_model = getattr(
                remote,
                "model",
                None,
            )


            if remote_model is None:

                continue


            if (
                getattr(
                    remote_model._meta,
                    "label_lower",
                    "",
                )
                == "toolkit.service"
            ):

                service_field = field
                break


        # Do not invent relationships between unrelated
        # business records and Services.
        if service_field is None:

            continue


        # ----------------------------------------------------
        # SAFE BUSINESS TEXT FIELDS
        # ----------------------------------------------------

        searchable_fields = []


        for field in Model._meta.fields:

            if not isinstance(
                field,
                (
                    django_models.CharField,
                    django_models.TextField,
                ),
            ):

                continue


            name = field.name
            lowered = name.lower()


            if name in blocked_fields:

                continue


            if any(
                fragment in lowered
                for fragment
                in blocked_fragments
            ):

                continue


            searchable_fields.append(
                name
            )


        if not searchable_fields:

            continue


        condition = KnowledgeQ()


        for field_name in searchable_fields:

            condition |= _safe_text_condition(
                KnowledgeQ,
                field_name,
                query,
            )


        queryset = Model.objects.filter(
            condition
        )


        model_fields = {
            field.name
            for field in Model._meta.fields
        }


        # ----------------------------------------------------
        # BDE VISIBILITY
        # ----------------------------------------------------

        if "visibility" in model_fields:

            visibility_field = (
                Model._meta.get_field(
                    "visibility"
                )
            )


            valid_choices = {
                str(value)
                for value, label
                in (
                    visibility_field.choices
                    or []
                )
            }


            permitted = []


            if "BDE" in valid_choices:

                permitted.append(
                    "BDE"
                )


            if "BDE_ALLOWED" in valid_choices:

                permitted.append(
                    "BDE_ALLOWED"
                )


            # If a visibility-controlled model does not expose
            # a known BDE permission, do not search it.
            if not permitted:

                continue


            queryset = queryset.filter(
                visibility__in=permitted
            )


        if "is_active" in model_fields:

            queryset = queryset.filter(
                is_active=True
            )


        if "is_published" in model_fields:

            queryset = queryset.filter(
                is_published=True
            )


        ids = queryset.values_list(
            service_field.attname,
            flat=True,
        )


        service_ids.update(
            service_id
            for service_id
            in ids
            if service_id
        )


    return service_ids





# ============================================================
# SHORT_TECH_KEYWORD_SEARCH_V11
# ============================================================

_SHORT_TECH_PATTERNS = {

    "ai": (
        r"(^|[^A-Za-z0-9])"
        r"ai"
        r"([^A-Za-z0-9]|$)"
    ),

    "iot": (
        r"(^|[^A-Za-z0-9])"
        r"iot"
        r"([^A-Za-z0-9]|$)"
    ),
}


def _short_tech_pattern(
    query,
):

    normalized = str(
        query or ""
    ).strip().casefold()


    return (
        _SHORT_TECH_PATTERNS
        .get(
            normalized
        )
    )


def _short_tech_terms_in_query(
    query,
):
    """
    Detect explicit AI / IoT concepts inside
    longer natural-language searches.
    """

    import re


    text = str(
        query or ""
    ).casefold()


    result = []


    if (
        re.search(
            r"(^|[^a-z0-9])ai([^a-z0-9]|$)",
            text,
        )
        or
        "artificial intelligence"
        in text
    ):

        result.append(
            "ai"
        )


    if (
        re.search(
            r"(^|[^a-z0-9])iot([^a-z0-9]|$)",
            text,
        )
        or
        "internet of things"
        in text
    ):

        result.append(
            "iot"
        )


    return result


def _safe_text_condition(
    q_class,
    field_name,
    query,
):
    """
    AI and IoT use word/concept boundaries.

    Every other query keeps the existing
    icontains behaviour.
    """

    pattern = (
        _short_tech_pattern(
            query
        )
    )


    if pattern:

        return q_class(
            **{
                f"{field_name}__iregex":
                    pattern
            }
        )


    return q_class(
        **{
            f"{field_name}__icontains":
                query
        }
    )


def _exact_short_tech_ids(
    base_services,
    query,
):

    import re


    pattern_text = (
        _short_tech_pattern(
            query
        )
    )


    if not pattern_text:

        return None


    # --------------------------------------------------------
    # CORE SERVICE TEXT
    # --------------------------------------------------------

    result = set(
        base_services
        .filter(
            search_text_filter(
                query
            )
        )
        .distinct()
        .values_list(
            "pk",
            flat=True,
        )
    )


    # --------------------------------------------------------
    # BDE BUSINESS KNOWLEDGE
    # --------------------------------------------------------

    result.update(
        business_knowledge_match_ids(
            query
        )
    )


    # --------------------------------------------------------
    # STRUCTURED INDUSTRIES
    #
    # IMPORTANT:
    # all_bde_services() has select_related().
    # Clear it before only() so related fields
    # are not deferred/traversed simultaneously.
    # --------------------------------------------------------

    regex = re.compile(
        pattern_text,
        flags=re.I,
    )


    industry_queryset = (
        base_services
        .select_related(
            None
        )
        .only(
            "pk",
            "industries",
        )
    )


    for service in industry_queryset:

        industries = (
            service.industries
            or []
        )


        if isinstance(
            industries,
            (
                list,
                tuple,
                set,
            ),
        ):

            text = " ".join(
                str(value)
                for value in industries
                if value
            )

        else:

            text = str(
                industries
            )


        if regex.search(
            text
        ):

            result.add(
                service.pk
            )


    return result


def _guard_short_tech_results(
    base_services,
    query,
    service_ids,
):
    """
    When AI or IoT is explicitly requested,
    require genuine AI/IoT evidence.
    """

    result = set(
        service_ids
    )


    for term in (
        _short_tech_terms_in_query(
            query
        )
    ):

        exact_ids = (
            _exact_short_tech_ids(
                base_services,
                term,
            )
        )


        if exact_ids is not None:

            result &= set(
                exact_ids
            )


    return result


def search_text_filter(query):
    return (
        _safe_text_condition(
            Q,
            "sales_pitch",
            query,
        )
        | _safe_text_condition(
            Q,
            "subsidy_details",
            query,
        )
        | _safe_text_condition(
            Q,
            "funding_type",
            query,
        )
        | _safe_text_condition(
            Q,
            "service_kind",
            query,
        )
        | _safe_text_condition(
            Q,
            "classifications__name",
            query,
        )
        | _safe_text_condition(
            Q,
            "category__name",
            query,
        )
        | _safe_text_condition(
            Q,
            "domain__name",
            query,
        )
        | _safe_text_condition(
            Q,
            "application_deadline_raw",
            query,
        )
        | _safe_text_condition(
            Q,
            "funding_organisation",
            query,
        )
        | _safe_text_condition(
            Q,
            "applicable_for_raw",
            query,
        )
        | _safe_text_condition(
            Q,
            "eligibility_summary",
            query,
        )
        | _safe_text_condition(
            Q,
            "benefits",
            query,
        )
        | _safe_text_condition(
            Q,
            "overview",
            query,
        )
        | _safe_text_condition(
            Q,
            "bde_summary",
            query,
        )
        | _safe_text_condition(
            Q,
            "title",
            query,
        )
        | _safe_text_condition(
            Q,
            "service_id",
            query,
        )
    )



def _natural_variant_match_ids(
    base_services,
    variants,
):
    """
    Search one natural-language concept against the same
    trusted V1 data surfaces.
    """

    condition = Q()


    for variant in variants:

        condition |= search_text_filter(
            variant
        )


    service_ids = set(
        base_services
        .filter(
            condition
        )
        .distinct()
        .values_list(
            "pk",
            flat=True,
        )
    )


    for variant in variants:

        service_ids.update(
            sector_match_ids(
                base_services,
                variant,
            )
        )


        service_ids.update(
            business_knowledge_match_ids(
                variant
            )
        )


    return service_ids


def natural_language_match_ids(
    base_services,
    query,
):
    """
    Deterministic English/Hinglish search.

    Existing concept matching remains unchanged.

    AI / IoT additionally require real
    keyword evidence to avoid substring matches.
    """

    from .search_intelligence import (
        query_groups,
    )


    groups = query_groups(
        query
    )


    if not groups:

        return set()


    matched_groups = [
        _natural_variant_match_ids(
            base_services,
            variants,
        )
        for variants in groups
    ]


    if len(
        matched_groups
    ) == 1:

        return _guard_short_tech_results(
            base_services,
            query,
            matched_groups[
                0
            ],
        )


    if all(
        matched_groups
    ):

        intersection = set.intersection(
            *matched_groups
        )


        if intersection:

            return _guard_short_tech_results(
                base_services,
                query,
                intersection,
            )


    scores = {}


    for matched_ids in matched_groups:

        for service_id in matched_ids:

            scores[
                service_id
            ] = (
                scores.get(
                    service_id,
                    0,
                )
                + 1
            )


    group_count = len(
        matched_groups
    )


    if group_count <= 2:

        threshold = group_count

    elif group_count == 3:

        threshold = 2

    else:

        threshold = max(
            2,
            group_count - 1,
        )


    result = {
        service_id
        for service_id, score
        in scores.items()
        if score >= threshold
    }


    return _guard_short_tech_results(
        base_services,
        query,
        result,
    )




def _search_money_amounts(value):
    """
    Extract monetary values and normalize them to lakh units.

    5 lakh  -> 5
    25 lakh -> 25
    1 crore -> 100

    This prevents substring mistakes such as
    5 lakh matching 25 lakh.
    """

    import re

    from decimal import Decimal


    text = str(
        value or ""
    ).casefold()


    pattern = re.compile(
        r"(?<![0-9])"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*"
        r"(lakh|lakhs|lac|lacs|crore|crores|cr)"
        r"\b"
    )


    amounts = set()


    for number, unit in pattern.findall(
        text
    ):

        amount = Decimal(
            number
        )


        if unit in {
            "crore",
            "crores",
            "cr",
        }:

            amount *= Decimal(
                "100"
            )


        amounts.add(
            amount
        )


    return amounts


def natural_language_rank_map(
    base_services,
    query,
):
    """
    Rank existing V2A.1 candidates.

    This DOES NOT change search recall.
    It only determines which relevant Services appear first.

    Scores are internal only.
    """

    from .search_intelligence import (
        normalize_query,
        query_groups,
    )


    groups = query_groups(
        query
    )


    if not groups:

        return {}


    matched_groups = [
        _natural_variant_match_ids(
            base_services,
            variants,
        )
        for variants in groups
    ]


    candidate_ids = set()


    for matched_ids in matched_groups:

        candidate_ids.update(
            matched_ids
        )


    if not candidate_ids:

        return {}


    services = list(
        base_services
        .filter(
            pk__in=candidate_ids
        )
        .select_related(
            "domain",
            "category",
        )
        .distinct()
    )


    query_amounts = (
        _search_money_amounts(
            query
        )
    )


    scores = {}


    for service in services:

        values = (
            service.title,
            service.service_id,
            service.bde_summary,
            service.overview,
            service.benefits,
            service.eligibility_summary,
            service.applicable_for_raw,
            service.funding_organisation,
            service.funding_type,
            service.subsidy_details,
            service.sales_pitch,
            service.restrictions,
            service.important_notes,
        )


        raw_text = " ".join(
            str(value)
            for value in values
            if value
        )


        core_text = normalize_query(
            raw_text
        )


        service_amounts = (
            _search_money_amounts(
                raw_text
            )
        )


        score = 0
        true_matches = 0


        for variants, matched_ids in zip(
            groups,
            matched_groups,
        ):

            group_amounts = set()


            for variant in variants:

                group_amounts.update(
                    _search_money_amounts(
                        variant
                    )
                )


            # =================================================
            # NUMERIC CONCEPT
            # =================================================

            if group_amounts:

                if (
                    query_amounts
                    & service_amounts
                ):

                    true_matches += 1

                    # Exact amount evidence.
                    score += 2500


                elif (
                    query_amounts
                    and service_amounts
                    and any(
                        available
                        >= requested
                        for available
                        in service_amounts
                        for requested
                        in query_amounts
                    )
                ):

                    # Can potentially provide at least
                    # requested amount, but isn't exact.
                    score += 120


                continue


            # =================================================
            # NORMAL BUSINESS CONCEPT
            # =================================================

            if service.pk not in matched_ids:

                continue


            true_matches += 1
            score += 450


            title = normalize_query(
                service.title
            )


            category = normalize_query(
                service.category.name
                if service.category
                else ""
            )


            domain = normalize_query(
                service.domain.name
                if service.domain
                else ""
            )


            normalized_variants = [
                normalize_query(
                    variant
                )
                for variant in variants
                if variant
            ]


            if any(
                variant
                and variant in title
                for variant
                in normalized_variants
            ):

                score += 350


            if any(
                variant
                and variant in core_text
                for variant
                in normalized_variants
            ):

                score += 220


            if any(
                variant
                and (
                    variant in category
                    or variant in domain
                )
                for variant
                in normalized_variants
            ):

                score += 100


        # =====================================================
        # FULL-INTENT BONUS
        # =====================================================

        if true_matches == len(
            groups
        ):

            score += 1500


        elif (
            len(groups) >= 3
            and true_matches
            == len(groups) - 1
        ):

            score += 200


        scores[
            service.pk
        ] = score


    return scores


def search_relevance_sort_key(
    service,
    relevance_scores,
    query,
    domain_tiebreak=False,
):
    """
    Shared relevance order for:

    - Business Toolkit
    - live search suggestions
    - Service Library
    """

    from .search_intelligence import (
        normalize_query,
    )


    score = int(
        relevance_scores.get(
            service.pk,
            0,
        )
    )


    query_text = normalize_query(
        query
    )


    title = normalize_query(
        service.title
    )


    # Known Service name searches stay strongest.
    if (
        query_text
        and title == query_text
    ):

        score += 5000


    elif (
        query_text
        and title.startswith(
            query_text
        )
    ):

        score += 1800


    elif (
        query_text
        and query_text in title
    ):

        score += 900


    domain_order = 0


    if domain_tiebreak:

        domain_order = getattr(
            service.domain,
            "display_order",
            9999,
        )


    return (
        -score,
        domain_order,
        title,
    )




def _source_sort_key(source):
    return (
        SOURCE_PRIORITY.get(
            source.source_kind,
            99,
        ),
        0 if source.is_official else 1,
        source.pk or 0,
    )


def _deadline_label(service):
    if service.application_deadline:
        return service.application_deadline.strftime(
            "%d %b %Y"
        )

    raw = (
        service.application_deadline_raw
        or ""
    ).strip()

    if raw:
        return raw

    if service.deadline_status not in {
        "",
        "UNKNOWN",
    }:
        return service.get_deadline_status_display()

    return "Not recorded"


def _attach_bde_ui(service):
    apply_pitch_state(service)

    sources = [
        source
        for source
        in service.sources.all()
        if source.source_url
    ]

    sources.sort(
        key=_source_sort_key
    )

    service.bde_sources = sources
    service.primary_source = (
        sources[0]
        if sources
        else None
    )

    service.bde_deadline_label = (
        _deadline_label(service)
    )

    return service


def _attach_bde_ui_many(services):
    for service in services:
        _attach_bde_ui(service)

    return services


def _remember_recent(request, service):
    recent = list(
        request.session.get(
            "bde_recent_service_ids",
            [],
        )
    )

    service_id = int(service.pk)

    recent = [
        item
        for item
        in recent
        if int(item) != service_id
    ]

    recent.insert(
        0,
        service_id,
    )

    request.session[
        "bde_recent_service_ids"
    ] = recent[:12]


def _serialize_service(
    request,
    service,
):
    _attach_bde_ui(service)
    _remember_recent(
        request,
        service,
    )

    summary = (
        service.bde_summary
        or service.overview
        or service.benefits
        or ""
    ).strip()

    sources = [
        {
            "name": (
                source.source_name
                or SOURCE_LABELS.get(
                    source.source_kind,
                    "External Link",
                )
            ),
            "label": SOURCE_LABELS.get(
                source.source_kind,
                "External Link",
            ),
            "kind": source.source_kind,
            "url": (
                f"/toolkit/service/{service.pk}/"
                f"source/{source.pk}/open/"
            ),
            "official": source.is_official,
        }
        for source
        in service.bde_sources
    ]

    return {
        "id": service.pk,
        "service_id": service.service_id,
        "title": service.title,
        "domain": service.domain.name,
        "category": service.category.name,
        "kind": (
            service.get_service_kind_display()
        ),
        "summary": summary,
        "benefits": service.benefits or "",
        "eligibility": (
            service.eligibility_summary
            or ""
        ),
        "applicable_for": (
            service.applicable_for_raw
            or ""
        ),
        "funding_organisation": (
            service.funding_organisation
            or ""
        ),
        "deadline": (
            service.bde_deadline_label
        ),
        "pitch_state": (
            service.pitch_state_label
        ),
        "pitch_state_code": (
            service.pitch_state_code
        ),
        "primary_url": (
            (
                f"/toolkit/service/{service.pk}/source/"
                f"{service.primary_source.pk}/open/"
            )
            if service.primary_source
            else ""
        ),
        "detail_url": (
            f"/toolkit/service/{service.slug}/"
        ),
        "sources": sources,
        "requirements": [
            {
                "name": item.name,
                "description": (
                    item.description
                    or ""
                ),
                "mandatory": (
                    item.is_mandatory
                ),
            }
            for item
            in service.document_requirements.all()
        ],
        "process": [
            {
                "number": item.step_number,
                "title": item.title,
                "description": (
                    item.description
                    or ""
                ),
            }
            for item
            in service.process_steps.all()
        ],
        "saved": SavedService.objects.filter(
            user=request.user,
            service=service,
        ).exists(),
    }


@login_required
def toolkit_home(request):
    # BDE search is now a complete published catalog search.
    # Pitch windows are displayed as state, not used to hide valid records.
    base_services = all_bde_services()

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


    if query:
        sector_ids = sector_match_ids(
            base_services,
            query
        )

        services = services.filter(
            search_text_filter(query)
            | Q(pk__in=sector_ids)
            | Q(
                pk__in=business_knowledge_match_ids(
                    query
                )
            )
            | Q(
                pk__in=natural_language_match_ids(
                    base_services,
                    query
                )
            )
        ).distinct()


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
        category_pk = int(
            category_id
        )

        services = services.filter(
            Q(category_id=category_pk)
            | Q(
                classifications__id=(
                    category_pk
                )
            )
        ).distinct()


    valid_kinds = {
        value
        for value, label
        in Service.SERVICE_KIND_CHOICES
    }

    if service_kind in valid_kinds:
        services = services.filter(
            service_kind=service_kind
        )


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


    if query:

        relevance_scores = (
            natural_language_rank_map(
                base_services,
                query,
            )
        )

        service_list = list(
            services.select_related(
                "domain",
                "category",
            )
        )

        service_list.sort(
            key=lambda service:
                search_relevance_sort_key(
                    service,
                    relevance_scores,
                    query,
                    domain_tiebreak=True,
                )
        )

        service_list = (
            service_list[:250]
        )

    else:

        service_list = list(
            services.order_by(
                "domain__display_order",
                "title"
            )[:250]
        )

    _attach_bde_ui_many(
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
    """
    BharatNXT Smart Instant Typeahead V3.

    Purpose:
    - instant dropdown while the BDE types
    - include BDE-visible supporting Toolkit knowledge
    - understand common business wording variations
    - preserve token-safe AI / IoT behaviour

    This is NOT the authoritative full Search V2.

    Pressing Enter still runs toolkit_home() and the complete
    Search V2 intelligence.
    """

    from time import monotonic

    from .models import (
        ServiceContentSection,
    )


    query = request.GET.get(
        "q",
        ""
    ).strip()


    if len(query) < 2:

        return JsonResponse(
            {
                "results": []
            }
        )


    # =====================================================
    # NORMALISE TEXT
    # =====================================================

    def normalize(value):

        text = str(
            value or ""
        ).casefold()


        chars = []

        previous_space = False


        for char in text:

            if char.isalnum():

                chars.append(
                    char
                )

                previous_space = False

            else:

                if not previous_space:

                    chars.append(
                        " "
                    )

                    previous_space = True


        return " ".join(
            "".join(
                chars
            ).split()
        )


    # =====================================================
    # SEARCH LANGUAGE NORMALISATION
    #
    # Phrase aliases handle abbreviations.
    # Word aliases handle safe singular/plural/common variants.
    #
    # We deliberately DO NOT use aggressive stemming because
    # that can create false positives in business searches.
    # =====================================================

    phrase_aliases = (
        (
            "artificial intelligence",
            "ai",
        ),
        (
            "internet of things",
            "iot",
        ),
        (
            "fin tech",
            "fintech",
        ),
        (
            "financial technology",
            "fintech",
        ),
        (
            "women led",
            "woman led",
        ),
        (
            "female led",
            "woman led",
        ),
        (
            "female entrepreneur",
            "woman entrepreneur",
        ),
        (
            "female entrepreneurs",
            "woman entrepreneur",
        ),
    )


    word_aliases = {
        "women":
            "woman",

        "womens":
            "woman",

        "female":
            "woman",
        "mahila":
            "woman",

        "mahilaon":
            "woman",

        "females":
            "woman",

        "entrepreneurs":
            "entrepreneur",

        "startups":
            "startup",

        "schemes":
            "scheme",

        "grants":
            "grant",

        "loans":
            "loan",

        "founders":
            "founder",

        "companies":
            "company",

        "businesses":
            "business",

        "industries":
            "industry",

        "technologies":
            "technology",

        "agricultural":
            "agriculture",
    }


    def canonicalize(value):

        text = normalize(
            value
        )


        for source, replacement in (
            phrase_aliases
        ):

            text = text.replace(
                source,
                replacement,
            )


        tokens = []


        for token in text.split():

            tokens.append(
                word_aliases.get(
                    token,
                    token,
                )
            )


        return " ".join(
            tokens
        )


    query_canonical = canonicalize(
        query
    )


    query_terms = (
        query_canonical.split()
    )


    if not query_terms:

        return JsonResponse(
            {
                "results": []
            }
        )


    # =====================================================
    # FAST CACHE
    #
    # Query 1:
    # Service catalogue
    #
    # Query 2:
    # All BDE-visible ServiceContentSection knowledge
    #
    # Warm requests:
    # 0 SQL
    #
    # No per-service queries.
    # =====================================================

    now = monotonic()


    cache = getattr(
        search_suggestions,
        "_bnx_fast_catalog_cache_v3",
        None,
    )


    if (
        not cache
        or
        now - cache[
            "created_at"
        ] > 10.0
    ):

        catalogue = list(
            Service.objects
            .filter(
                status__in=VISIBLE_STATUSES
            )
            .values(
                "id",
                "title",
                "service_id",
                "slug",
                "service_kind",
                "industries",

                "domain__name",
                "category__name",

                "bde_summary",
                "overview",
                "benefits",
                "eligibility_summary",
                "applicable_for_raw",

                "funding_organisation",
                "funding_type",
                "subsidy_details",
                "sales_pitch",
                "application_deadline_raw",
            )
        )


        by_service_id = {
            row["id"]: row
            for row in catalogue
        }


        for row in catalogue:

            row[
                "_bde_content"
            ] = []


        # -------------------------------------------------
        # BDE business knowledge only.
        #
        # ADMIN_ONLY content is deliberately excluded.
        # -------------------------------------------------

        content_rows = (
            ServiceContentSection.objects
            .filter(
                service_id__in=(
                    by_service_id.keys()
                ),
                visibility="BDE",
            )
            .values_list(
                "service_id",
                "title",
                "content",
            )
        )


        for (
            service_id,
            section_title,
            section_content,
        ) in content_rows:

            target = (
                by_service_id.get(
                    service_id
                )
            )


            if target is None:

                continue


            if section_title:

                target[
                    "_bde_content"
                ].append(
                    str(
                        section_title
                    )
                )


            if section_content:

                target[
                    "_bde_content"
                ].append(
                    str(
                        section_content
                    )
                )


        # Pre-canonicalise once.
        #
        # Search requests after this point only scan
        # small in-memory strings.

        kind_labels = dict(
            Service.SERVICE_KIND_CHOICES
        )


        prepared = []


        for row in catalogue:

            title = str(
                row.get(
                    "title"
                )
                or ""
            )

            service_id = str(
                row.get(
                    "service_id"
                )
                or ""
            )

            domain = str(
                row.get(
                    "domain__name"
                )
                or ""
            )

            category = str(
                row.get(
                    "category__name"
                )
                or ""
            )

            kind = str(
                kind_labels.get(
                    row.get(
                        "service_kind"
                    ),
                    row.get(
                        "service_kind"
                    )
                    or "",
                )
            )


            industries_value = (
                row.get(
                    "industries"
                )
            )


            if isinstance(
                industries_value,
                (
                    list,
                    tuple,
                    set,
                ),
            ):

                industries = " ".join(
                    str(
                        item or ""
                    )
                    for item
                    in industries_value
                )

            else:

                industries = str(
                    industries_value
                    or ""
                )


            direct_business_text = " ".join(
                str(
                    row.get(
                        field
                    )
                    or ""
                )

                for field in (
                    "bde_summary",
                    "overview",
                    "benefits",
                    "eligibility_summary",
                    "applicable_for_raw",
                    "funding_organisation",
                    "funding_type",
                    "subsidy_details",
                    "sales_pitch",
                    "application_deadline_raw",
                )
            )


            bde_content = " ".join(
                row.get(
                    "_bde_content",
                    []
                )
            )


            title_c = canonicalize(
                title
            )

            service_id_c = canonicalize(
                service_id
            )

            domain_c = canonicalize(
                domain
            )

            category_c = canonicalize(
                category
            )

            kind_c = canonicalize(
                kind
            )

            industries_c = canonicalize(
                industries
            )

            direct_c = canonicalize(
                direct_business_text
            )

            bde_content_c = canonicalize(
                bde_content
            )


            combined_c = " ".join(
                value

                for value in (
                    title_c,
                    service_id_c,
                    domain_c,
                    category_c,
                    kind_c,
                    industries_c,
                    direct_c,
                    bde_content_c,
                )

                if value
            )


            prepared.append(
                {
                    "id":
                        row["id"],

                    "title":
                        title,

                    "service_id":
                        service_id,

                    "slug":
                        str(
                            row.get(
                                "slug"
                            )
                            or ""
                        ),

                    "domain":
                        domain,

                    "category":
                        category,

                    "kind":
                        kind,

                    "title_c":
                        title_c,

                    "service_id_c":
                        service_id_c,

                    "domain_c":
                        domain_c,

                    "category_c":
                        category_c,

                    "kind_c":
                        kind_c,

                    "industries_c":
                        industries_c,

                    "direct_c":
                        direct_c,

                    "bde_content_c":
                        bde_content_c,

                    "combined_c":
                        combined_c,
                }
            )


        cache = {
            "created_at":
                now,

            "catalogue":
                prepared,
        }


        setattr(
            search_suggestions,
            "_bnx_fast_catalog_cache_v3",
            cache,
        )


    catalogue = cache[
        "catalogue"
    ]


    # =====================================================
    # SAFE MATCHING
    # =====================================================

    def matches_terms(
        text
    ):

        if not text:

            return False


        tokens = set(
            text.split()
        )


        for term in query_terms:

            # ---------------------------------------------
            # Short technology terms MUST be token exact.
            #
            # AI must not match "paid".
            # IoT must not match letters inside a word.
            # ---------------------------------------------

            if len(term) <= 3:

                if term not in tokens:

                    return False

            else:

                if term not in text:

                    return False


        return True


    matches = []


    # =====================================================
    # RANK
    # =====================================================

    for row in catalogue:

        if not matches_terms(
            row[
                "combined_c"
            ]
        ):

            continue


        title_c = row[
            "title_c"
        ]


        # Exact / title matches first.

        if (
            title_c
            == query_canonical
        ):

            rank = 0


        elif (
            len(
                query_canonical
            ) > 3
            and
            title_c.startswith(
                query_canonical
            )
        ):

            rank = 1


        elif matches_terms(
            title_c
        ):

            rank = 2


        elif (
            matches_terms(
                row[
                    "category_c"
                ]
            )
            or
            matches_terms(
                row[
                    "domain_c"
                ]
            )
        ):

            rank = 3


        elif matches_terms(
            row[
                "industries_c"
            ]
        ):

            rank = 4


        elif matches_terms(
            row[
                "direct_c"
            ]
        ):

            rank = 5


        elif matches_terms(
            row[
                "bde_content_c"
            ]
        ):

            rank = 6


        else:

            rank = 7


        matches.append(
            (
                rank,

                row[
                    "title"
                ].casefold(),

                {
                    "pk":
                        row[
                            "id"
                        ],

                    "title":
                        row[
                            "title"
                        ],

                    "service_id":
                        row[
                            "service_id"
                        ],

                    "domain":
                        row[
                            "domain"
                        ],

                    "category":
                        row[
                            "category"
                        ],

                    "kind":
                        row[
                            "kind"
                        ],

                    "url":
                        (
                            "/toolkit/service/"
                            + row[
                                "slug"
                            ]
                            + "/"
                        ),
                },
            )
        )


    matches.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )


    results = [
        item[2]
        for item
        in matches[:8]
    ]


    return JsonResponse(
        {
            "results":
                results
        }
    )






@login_required
def service_library(request):
    base_services = all_bde_services()

    query = request.GET.get(
        "q",
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

    selected_service_id = (
        request.GET.get(
            "service",
            ""
        ).strip()
    )


    # Build category counts from the complete BDE catalog.
    catalog_services = list(
        base_services.order_by(
            "title"
        )
    )

    category_counts = {}

    for service in catalog_services:
        category_ids = {
            service.category_id
        }

        category_ids.update(
            category.pk
            for category
            in service.classifications.all()
        )

        for item_id in category_ids:
            category_counts[
                item_id
            ] = (
                category_counts.get(
                    item_id,
                    0
                )
                + 1
            )


    category_items = list(
        Category.objects
        .filter(is_active=True)
        .select_related("domain")
        .order_by(
            "domain__display_order",
            "domain__name",
            "display_order",
            "name",
        )
    )

    for item in category_items:
        item.bde_count = (
            category_counts.get(
                item.pk,
                0
            )
        )


    services = base_services

    if query:
        sector_ids = sector_match_ids(
            base_services,
            query
        )

        services = services.filter(
            search_text_filter(query)
            | Q(pk__in=sector_ids)
            | Q(
                pk__in=business_knowledge_match_ids(
                    query
                )
            )
            | Q(
                pk__in=natural_language_match_ids(
                    base_services,
                    query
                )
            )
        ).distinct()


    if category_id.isdigit():
        category_pk = int(
            category_id
        )

        services = services.filter(
            Q(category_id=category_pk)
            | Q(
                classifications__id=(
                    category_pk
                )
            )
        ).distinct()


    valid_kinds = {
        value
        for value, label
        in Service.SERVICE_KIND_CHOICES
    }

    if service_kind in valid_kinds:
        services = services.filter(
            service_kind=service_kind
        )


    result_count = services.count()

    library_filters = {
        "category": category_id,
        "service_kind": service_kind,
    }

    if any(library_filters.values()):
        SearchEvent.objects.create(
            user=request.user,
            event_type="FILTER",
            query="",
            filters={
                **library_filters,
                "_source": "service_library",
            },
            result_count=result_count,
        )

        log_activity(
            request,
            "FILTER",
            "Service Library filters applied.",
            metadata={
                **library_filters,
                "result_count": result_count,
                "source": "service_library",
            },
        )

    if query:
        SearchEvent.objects.create(
            user=request.user,
            event_type="SEARCH",
            query=query[:255],
            filters={"_source": "service_library"},
            result_count=result_count,
        )
        log_activity(
            request,
            "SEARCH",
            f'Toolkit search: "{query[:255]}"',
            metadata={
                "query": query[:255],
                "result_count": result_count,
                "source": "service_library",
            },
        )

    if query:

        relevance_scores = (
            natural_language_rank_map(
                base_services,
                query,
            )
        )

        service_list = list(
            services.select_related(
                "domain",
                "category",
            )
        )

        service_list.sort(
            key=lambda service:
                search_relevance_sort_key(
                    service,
                    relevance_scores,
                    query,
                )
        )

        service_list = (
            service_list[:300]
        )

    else:

        service_list = list(
            services.order_by(
                "title"
            )[:300]
        )

    _attach_bde_ui_many(
        service_list
    )


    selected_service = None

    if selected_service_id.isdigit():
        selected_pk = int(
            selected_service_id
        )

        selected_service = next(
            (
                item
                for item
                in service_list
                if item.pk == selected_pk
            ),
            None,
        )

        if selected_service is None:
            selected_service = (
                all_bde_services()
                .filter(
                    pk=selected_pk
                )
                .first()
            )

            if selected_service:
                _attach_bde_ui(
                    selected_service
                )


    if (
        selected_service is None
        and service_list
    ):
        selected_service = (
            service_list[0]
        )


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
        "toolkit/service_library.html",
        {
            "services": service_list,
            "result_count": len(
                service_list
            ),
            "total_service_count": len(
                catalog_services
            ),
            "categories": category_items,
            "selected_category": (
                category_id
            ),
            "selected_kind": (
                service_kind
            ),
            "service_kinds": (
                Service.SERVICE_KIND_CHOICES
            ),
            "query": query,
            "selected_service": (
                selected_service
            ),
            "saved_service_ids": (
                saved_service_ids
            ),
        }
    )


@login_required
def service_quick_view(
    request,
    service_id,
):
    service = get_object_or_404(
        all_bde_services(),
        pk=service_id,
    )

    log_activity(
        request,
        "SERVICE_VIEW",
        f"Quick viewed service: {service.title}.",
        target_type="service",
        target_id=service.pk,
        metadata={
            "service_id": service.service_id,
            "domain": service.domain.name,
            "category": service.category.name,
            "view_mode": "quick",
        },
    )

    search_query = " ".join(
        request.GET.get("search_q", "").split()
    )[:255]

    if len(search_query) >= 2:
        SearchEvent.objects.create(
            user=request.user,
            event_type="SEARCH",
            query=search_query,
            filters={"_source": "instant_suggestion"},
            result_count=1,
            selected_service=service,
        )
        log_activity(
            request,
            "SEARCH",
            f'Toolkit search: "{search_query}"',
            target_type="service",
            target_id=service.pk,
            metadata={
                "query": search_query,
                "result_count": 1,
                "source": "instant_suggestion",
                "selected_service_id": service.pk,
            },
        )

    return JsonResponse(
        _serialize_service(
            request,
            service,
        )
    )


@login_required
def service_detail(request, slug):
    service = get_object_or_404(
        all_bde_services(),
        slug=slug
    )

    _attach_bde_ui(
        service
    )

    _remember_recent(
        request,
        service,
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
            "view_mode": "full",
        },
    )


    is_saved = SavedService.objects.filter(
        user=request.user,
        service=service,
    ).exists()


    eligibility_rules = list(
        service.eligibility_rules
        .all()
        .order_by(
            "display_order",
            "id",
        )
    )


    document_requirements = list(
        service.document_requirements
        .all()
        .order_by(
            "display_order",
            "name",
        )
    )


    process_steps = list(
        service.process_steps
        .all()
        .order_by(
            "step_number",
            "id",
        )
    )


    content_sections = list(
        service.content_sections
        .filter(
            visibility="BDE"
        )
        .order_by(
            "display_order",
            "id",
        )
    )


    # -------------------------------------------------
    # First-screen source wording.
    #
    # These values are taken directly from the approved
    # imported Toolkit sections. They are intentionally
    # not summarized, truncated, rewritten or normalized.
    # -------------------------------------------------

    verbatim_benefit_parts = []
    verbatim_focus_sector_parts = []
    verbatim_eligibility_parts = []


    def append_verbatim(target, value):
        text = str(value or "")

        if text.strip() and text not in target:
            target.append(text)


    def format_verbatim_list_layout(value):
        """
        Add display-only line breaks to imported inline lists.

        Words, punctuation and database values remain unchanged.
        Existing line breaks are preserved.
        """

        import re

        text = str(value or "")

        marker_patterns = (
            r"(?:\(\d{1,2}\)|\d{1,2}[.)])(?=[ \t])",
            r"Voucher[ \t]+[A-Z][ \t]*:",
        )

        for marker_pattern in marker_patterns:
            markers = re.findall(
                marker_pattern,
                text,
                flags=re.IGNORECASE,
            )

            if len(markers) < 2:
                continue

            text = re.sub(
                rf"[ \t]+(?={marker_pattern})",
                "\n",
                text,
                flags=re.IGNORECASE,
            )

        return text


    for section in content_sections:
        title_key = str(
            section.title or ""
        ).strip().casefold()

        for prefix in (
            "fields.",
            "fields:",
        ):
            if title_key.startswith(prefix):
                title_key = title_key[len(prefix):].strip()
                break

        section_type = str(
            section.section_type or ""
        ).strip().upper()

        if (
            section_type == "BENEFITS"
            or title_key in {
                "benefit",
                "benefits",
            }
        ):
            append_verbatim(
                verbatim_benefit_parts,
                section.content,
            )

        if (
            "focus sector" in title_key
            or title_key in {
                "sector",
                "sectors",
            }
        ):
            append_verbatim(
                verbatim_focus_sector_parts,
                section.content,
            )

        if (
            section_type == "ELIGIBILITY"
            or title_key in {
                "eligibility",
                "eligibility criteria",
                "eligibility criterion",
            }
        ):
            append_verbatim(
                verbatim_eligibility_parts,
                section.content,
            )


    if not verbatim_benefit_parts:
        append_verbatim(
            verbatim_benefit_parts,
            service.benefits,
        )


    if not verbatim_focus_sector_parts:
        industries = service.industries or []

        if isinstance(
            industries,
            (list, tuple),
        ):
            append_verbatim(
                verbatim_focus_sector_parts,
                "\n".join(
                    str(item)
                    for item in industries
                    if str(item).strip()
                ),
            )
        else:
            append_verbatim(
                verbatim_focus_sector_parts,
                industries,
            )


    if not verbatim_eligibility_parts:
        append_verbatim(
            verbatim_eligibility_parts,
            service.eligibility_summary,
        )


    if not verbatim_eligibility_parts:
        append_verbatim(
            verbatim_eligibility_parts,
            service.applicable_for_raw,
        )


    verbatim_benefits = "\n\n".join(
        verbatim_benefit_parts
    )

    verbatim_focus_sectors = "\n\n".join(
        verbatim_focus_sector_parts
    )

    verbatim_eligibility = "\n\n".join(
        verbatim_eligibility_parts
    )


    verbatim_benefits = format_verbatim_list_layout(
        verbatim_benefits
    )

    verbatim_focus_sectors = format_verbatim_list_layout(
        verbatim_focus_sectors
    )

    verbatim_eligibility = format_verbatim_list_layout(
        verbatim_eligibility
    )


    commercial_terms = list(
        service.commercial_terms
        .filter(
            visibility="BDE_ALLOWED",
            is_active=True,
        )
        .order_by(
            "id"
        )
    )


    knowledge_sections = list(
        service.knowledge_sections
        .filter(
            visibility="BDE"
        )
        .select_related(
            "document"
        )
        .order_by(
            "document__title",
            "display_order",
            "id",
        )
    )


    comparison_entries = list(
        service.comparison_entries
        .select_related(
            "matrix"
        )
        .order_by(
            "matrix__name",
            "row_number",
            "id",
        )
    )


    return render(
        request,
        "toolkit/service_detail.html",
        {
            "service":
                service,

            "is_saved":
                is_saved,

            "sources":
                service.bde_sources,

            "primary_source":
                service.primary_source,

            "classification_categories":
                list(
                    service.classifications.all()
                ),

            "eligibility_rules":
                eligibility_rules,

            "document_requirements":
                document_requirements,

            "process_steps":
                process_steps,

            "content_sections":
                content_sections,

            "verbatim_benefits":
                verbatim_benefits,

            "verbatim_focus_sectors":
                verbatim_focus_sectors,

            "verbatim_eligibility":
                verbatim_eligibility,

            "commercial_terms":
                commercial_terms,

            "knowledge_sections":
                knowledge_sections,

            "comparison_entries":
                comparison_entries,
        }
    )


@login_required
def saved_services(request):
    """
    Collection-first Saved Services workspace.

    Existing SavedService rows with no collection membership
    automatically appear under Unsorted.
    """

    collections = list(
        SavedCollection.objects
        .filter(
            user=request.user
        )
        .prefetch_related(
            "items__saved_service__service"
        )
        .order_by(
            "-updated_at",
            "name",
        )
    )


    for collection in collections:

        collection.service_count = (
            len(
                collection.items.all()
            )
        )


    unsorted_items = list(
        SavedService.objects
        .filter(
            user=request.user,
            collection_items__isnull=True,
        )
        .select_related(
            "service",
            "service__domain",
            "service__category",
        )
        .order_by(
            "-created_at"
        )
    )


    return render(
        request,
        "toolkit/saved_services.html",
        {
            "collections":
                collections,

            "collection_count":
                len(collections),

            "unsorted_items":
                unsorted_items,

            "unsorted_count":
                len(unsorted_items),
        },
    )




@login_required
def recent_services(request):
    recent_ids = [
        int(item)
        for item
        in request.session.get(
            "bde_recent_service_ids",
            [],
        )
        if str(item).isdigit()
    ]

    services_by_id = {
        service.pk: service
        for service
        in all_bde_services().filter(
            pk__in=recent_ids
        )
    }

    services = [
        services_by_id[
            service_id
        ]
        for service_id
        in recent_ids
        if service_id
        in services_by_id
    ]

    _attach_bde_ui_many(
        services
    )

    return render(
        request,
        "toolkit/recent_services.html",
        {
            "services": services,
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
        status__in=visible_service_statuses(request.user),
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




# ============================================================
# BNW_EXTERNAL_LINK_TRACKING_V1
# ============================================================

@login_required
@require_GET
def service_source_open(
    request,
    service_id,
    source_id,
):
    service = get_object_or_404(
        Service,
        pk=service_id,
        status__in=visible_service_statuses(request.user),
    )

    source = get_object_or_404(
        ServiceSource.objects.exclude(source_url=""),
        pk=source_id,
        service=service,
    )

    log_activity(
        request,
        "EXTERNAL_LINK_OPEN",
        (
            f"Opened external source: "
            f"{source.source_name[:110]} for "
            f"{service.title[:80]}."
        ),
        target_type="service",
        target_id=service.pk,
        metadata={
            "service_id": service.service_id,
            "source_id": source.pk,
            "source_name": source.source_name,
            "source_kind": source.source_kind,
            "is_official": source.is_official,
        },
    )

    return redirect(source.source_url)


# ============================================================
# BNX_SAVED_COLLECTIONS_V1
# BNW_COLLECTION_ACTIVITY_TRACKING_V1
# ============================================================

@login_required
def saved_collection_detail(
    request,
    collection_id,
):

    collection = get_object_or_404(
        SavedCollection,
        pk=collection_id,
        user=request.user,
    )


    items = list(
        SavedCollectionItem.objects
        .filter(
            collection=collection
        )
        .select_related(
            "saved_service",
            "saved_service__service",
            "saved_service__service__domain",
            "saved_service__service__category",
        )
        .order_by(
            "-created_at"
        )
    )


    for item in items:

        apply_pitch_state(
            item.saved_service.service
        )


    return render(
        request,
        "toolkit/saved_collection_detail.html",
        {
            "collection":
                collection,

            "items":
                items,

            "service_count":
                len(items),
        },
    )


@login_required
@require_POST
def saved_collection_create(
    request,
):

    name = request.POST.get(
        "name",
        ""
    ).strip()


    note = request.POST.get(
        "note",
        ""
    ).strip()


    if not name:

        messages.error(
            request,
            "Enter a client or collection name.",
        )

        return redirect(
            "toolkit:saved_services"
        )


    existing = (
        SavedCollection.objects
        .filter(
            user=request.user,
            name__iexact=name,
        )
        .first()
    )


    if existing:

        messages.info(
            request,
            f'"{existing.name}" already exists.',
        )

        return redirect(
            "toolkit:saved_collection_detail",
            collection_id=existing.pk,
        )


    collection = (
        SavedCollection.objects.create(
            user=request.user,
            name=name[:150],
            note=note[:500],
        )
    )


    messages.success(
        request,
        f'Created client collection "{collection.name}".',
    )

    log_activity(
        request,
        "COLLECTION_CREATE",
        f'Created collection: "{collection.name[:180]}".',
        target_type="saved_collection",
        target_id=collection.pk,
        metadata={
            "collection_id": collection.pk,
            "collection_name": collection.name,
        },
    )


    return redirect(
        "toolkit:saved_collection_detail",
        collection_id=collection.pk,
    )


@login_required
@require_POST
def saved_collection_rename(
    request,
    collection_id,
):

    collection = get_object_or_404(
        SavedCollection,
        pk=collection_id,
        user=request.user,
    )


    name = request.POST.get(
        "name",
        ""
    ).strip()


    note = request.POST.get(
        "note",
        collection.note,
    ).strip()


    if not name:

        messages.error(
            request,
            "Collection name cannot be empty.",
        )

        return redirect(
            "toolkit:saved_collection_detail",
            collection_id=collection.pk,
        )


    conflict = (
        SavedCollection.objects
        .filter(
            user=request.user,
            name__iexact=name,
        )
        .exclude(
            pk=collection.pk
        )
        .exists()
    )


    if conflict:

        messages.error(
            request,
            "You already have a collection with that name.",
        )

        return redirect(
            "toolkit:saved_collection_detail",
            collection_id=collection.pk,
        )


    previous_name = collection.name

    collection.name = name[:150]
    collection.note = note[:500]

    collection.save(
        update_fields=[
            "name",
            "note",
            "updated_at",
        ]
    )


    messages.success(
        request,
        "Collection updated.",
    )

    log_activity(
        request,
        "COLLECTION_RENAME",
        (
            f'Renamed collection "{previous_name[:90]}" '
            f'to "{collection.name[:90]}".'
        ),
        target_type="saved_collection",
        target_id=collection.pk,
        metadata={
            "collection_id": collection.pk,
            "previous_name": previous_name,
            "collection_name": collection.name,
        },
    )


    return redirect(
        "toolkit:saved_collection_detail",
        collection_id=collection.pk,
    )


@login_required
@require_POST
def saved_collection_delete(
    request,
    collection_id,
):

    collection = get_object_or_404(
        SavedCollection,
        pk=collection_id,
        user=request.user,
    )


    name = collection.name
    collection_id = collection.pk
    item_count = collection.items.count()

    collection.delete()


    # SavedService rows themselves are intentionally retained.
    # They therefore fall back into Unsorted if they no longer
    # belong to another collection.


    messages.success(
        request,
        (
            f'Deleted collection "{name}". '
            "Its saved services were not deleted."
        ),
    )

    log_activity(
        request,
        "COLLECTION_DELETE",
        f'Deleted collection: "{name[:180]}".',
        target_type="saved_collection",
        target_id=collection_id,
        metadata={
            "collection_id": collection_id,
            "collection_name": name,
            "removed_item_count": item_count,
        },
    )


    return redirect(
        "toolkit:saved_services"
    )


@login_required
def saved_service_collection_state(
    request,
    service_id,
):

    service = get_object_or_404(
        Service,
        pk=service_id,
        status__in=(
            visible_service_statuses(
                request.user
            )
        ),
    )


    saved_service = (
        SavedService.objects
        .filter(
            user=request.user,
            service=service,
        )
        .first()
    )


    selected_ids = set()


    if saved_service:

        selected_ids = set(
            SavedCollectionItem.objects
            .filter(
                saved_service=saved_service,
                collection__user=request.user,
            )
            .values_list(
                "collection_id",
                flat=True,
            )
        )


    collections = list(
        SavedCollection.objects
        .filter(
            user=request.user
        )
        .order_by(
            "-updated_at",
            "name",
        )
    )


    return JsonResponse(
        {
            "service": {
                "id":
                    service.pk,

                "title":
                    service.title,

                "service_id":
                    service.service_id,
            },

            "saved":
                bool(
                    saved_service
                ),

            "collections": [
                {
                    "id":
                        collection.pk,

                    "name":
                        collection.name,

                    "note":
                        collection.note,

                    "selected":
                        (
                            collection.pk
                            in selected_ids
                        ),
                }

                for collection
                in collections
            ],
        }
    )


@login_required
@require_POST
def saved_service_collection_action(
    request,
    service_id,
):

    service = get_object_or_404(
        Service,
        pk=service_id,
        status__in=(
            visible_service_statuses(
                request.user
            )
        ),
    )


    action = request.POST.get(
        "action",
        ""
    ).strip()


    # --------------------------------------------------------
    # CREATE COLLECTION + ADD SERVICE
    # --------------------------------------------------------

    if action == "create_and_add":

        name = request.POST.get(
            "name",
            ""
        ).strip()


        note = request.POST.get(
            "note",
            ""
        ).strip()


        if not name:

            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Enter a client or collection name."
                    ),
                },
                status=400,
            )


        collection = (
            SavedCollection.objects
            .filter(
                user=request.user,
                name__iexact=name,
            )
            .first()
        )


        collection_created = collection is None

        if collection_created:

            collection = (
                SavedCollection.objects.create(
                    user=request.user,
                    name=name[:150],
                    note=note[:500],
                )
            )


        saved_service, saved_created = (
            SavedService.objects.get_or_create(
                user=request.user,
                service=service,
            )
        )


        _, item_created = (
            SavedCollectionItem.objects.get_or_create(
                collection=collection,
                saved_service=saved_service,
            )
        )


        collection.save(
            update_fields=[
                "updated_at"
            ]
        )

        if collection_created:
            log_activity(
                request,
                "COLLECTION_CREATE",
                f'Created collection: "{collection.name[:180]}".',
                target_type="saved_collection",
                target_id=collection.pk,
                metadata={
                    "collection_id": collection.pk,
                    "collection_name": collection.name,
                    "source": "save_service_popup",
                },
            )

        if saved_created:
            log_activity(
                request,
                "SERVICE_SAVE",
                f"Saved service: {service.title[:220]}.",
                target_type="service",
                target_id=service.pk,
                metadata={
                    "service_id": service.service_id,
                    "source": "save_service_popup",
                },
            )

        if item_created:
            log_activity(
                request,
                "COLLECTION_ADD_SERVICE",
                (
                    f'Added "{service.title[:100]}" to '
                    f'"{collection.name[:80]}".'
                ),
                target_type="service",
                target_id=service.pk,
                metadata={
                    "service_id": service.service_id,
                    "collection_id": collection.pk,
                    "collection_name": collection.name,
                },
            )


        return JsonResponse(
            {
                "ok": True,
                "saved": True,
                "collection_id":
                    collection.pk,

                "collection_name":
                    collection.name,
            }
        )


    # --------------------------------------------------------
    # TOGGLE SERVICE INSIDE AN EXISTING COLLECTION
    # --------------------------------------------------------

    if action == "toggle_collection":

        collection_id = request.POST.get(
            "collection_id",
            ""
        )


        if not str(
            collection_id
        ).isdigit():

            return JsonResponse(
                {
                    "ok": False,
                    "error": "Invalid collection.",
                },
                status=400,
            )


        collection = get_object_or_404(
            SavedCollection,
            pk=int(
                collection_id
            ),
            user=request.user,
        )


        saved_service, saved_created = (
            SavedService.objects.get_or_create(
                user=request.user,
                service=service,
            )
        )


        existing = (
            SavedCollectionItem.objects
            .filter(
                collection=collection,
                saved_service=saved_service,
            )
            .first()
        )


        if existing:

            existing.delete()
            selected = False

        else:

            SavedCollectionItem.objects.create(
                collection=collection,
                saved_service=saved_service,
            )

            selected = True


        collection.save(
            update_fields=[
                "updated_at"
            ]
        )

        if saved_created:
            log_activity(
                request,
                "SERVICE_SAVE",
                f"Saved service: {service.title[:220]}.",
                target_type="service",
                target_id=service.pk,
                metadata={
                    "service_id": service.service_id,
                    "source": "collection_toggle",
                },
            )

        collection_action = (
            "COLLECTION_ADD_SERVICE"
            if selected
            else "COLLECTION_REMOVE_SERVICE"
        )

        collection_verb = (
            "Added"
            if selected
            else "Removed"
        )

        collection_joiner = (
            "to"
            if selected
            else "from"
        )

        log_activity(
            request,
            collection_action,
            (
                f'{collection_verb} "{service.title[:100]}" '
                f'{collection_joiner} "{collection.name[:80]}".'
            ),
            target_type="service",
            target_id=service.pk,
            metadata={
                "service_id": service.service_id,
                "collection_id": collection.pk,
                "collection_name": collection.name,
                "selected": selected,
            },
        )


        return JsonResponse(
            {
                "ok": True,
                "saved": True,
                "selected":
                    selected,

                "collection_id":
                    collection.pk,
            }
        )


    # --------------------------------------------------------
    # REMOVE SERVICE FROM ALL SAVED SERVICES
    # --------------------------------------------------------

    if action == "remove_saved":

        saved_service = (
            SavedService.objects
            .filter(
                user=request.user,
                service=service,
            )
            .first()
        )


        if saved_service:
            collection_count = (
                saved_service.collection_items.count()
            )

            saved_service.delete()

            log_activity(
                request,
                "SERVICE_UNSAVE",
                f"Removed saved service: {service.title[:210]}.",
                target_type="service",
                target_id=service.pk,
                metadata={
                    "service_id": service.service_id,
                    "source": "save_service_popup",
                    "removed_collection_count": collection_count,
                },
            )


        return JsonResponse(
            {
                "ok": True,
                "saved": False,
            }
        )


    return JsonResponse(
        {
            "ok": False,
            "error": "Unsupported action.",
        },
        status=400,
    )


@login_required
@require_POST
def saved_collection_remove_item(
    request,
    collection_id,
    item_id,
):

    collection = get_object_or_404(
        SavedCollection,
        pk=collection_id,
        user=request.user,
    )


    item = get_object_or_404(
        SavedCollectionItem,
        pk=item_id,
        collection=collection,
    )


    service = item.saved_service.service

    service_title = service.title
    collection_id_value = collection.pk
    collection_name = collection.name

    item.delete()


    collection.save(
        update_fields=[
            "updated_at"
        ]
    )

    log_activity(
        request,
        "COLLECTION_REMOVE_SERVICE",
        (
            f'Removed "{service_title[:100]}" from '
            f'"{collection_name[:80]}".'
        ),
        target_type="service",
        target_id=service.pk,
        metadata={
            "service_id": service.service_id,
            "collection_id": collection_id_value,
            "collection_name": collection_name,
        },
    )


    messages.success(
        request,
        (
            f'Removed "{service_title}" '
            f'from "{collection.name}".'
        ),
    )


    return redirect(
        "toolkit:saved_collection_detail",
        collection_id=collection.pk,
    )
