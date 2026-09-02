"""
BharatNXT Wave — Intelligent Delta Engine V1

PURPOSE
-------
Compare a newly analysed Excel/CSV source against the
current Toolkit and show only meaningful business changes.

IMPORTANT
---------
READ ONLY.

This module:
- does NOT create Services
- does NOT update Services
- does NOT update ImportRows
- does NOT change ImportBatch status
- does NOT delete anything
"""

import hashlib
import re

from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.db import models

from toolkit.intelligence.ingestion import (
    analyse_file,
)

from toolkit.models import (
    ImportBatch,
    Service,
)


# ============================================================
# NORMALISATION
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):

        value = " ".join(
            str(item)
            for item in value
            if item not in {
                None,
                "",
            }
        )

    text = str(value).strip()

    if not text:
        return ""

    text = text.lower()

    text = text.replace(
        "\u00a0",
        " ",
    )

    text = re.sub(
        r"[₹,]",
        "",
        text,
    )

    text = re.sub(
        r"[^a-z0-9%./:+\- ]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_url(value):

    value = str(
        value or ""
    ).strip()

    if not value:
        return ""

    try:

        parsed = urlsplit(
            value
        )

        scheme = (
            parsed.scheme.lower()
        )

        hostname = (
            parsed.hostname.lower()
            if parsed.hostname
            else ""
        )

        port = (
            f":{parsed.port}"
            if parsed.port
            else ""
        )

        netloc = (
            hostname
            + port
        )

        path = (
            parsed.path.rstrip("/")
        )

        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                parsed.query,
                "",
            )
        )

    except Exception:

        return value.rstrip("/")


def sha256_file(path):

    digest = hashlib.sha256()

    with Path(path).open(
        "rb"
    ) as handle:

        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):

            digest.update(
                chunk
            )

    return digest.hexdigest()


# ============================================================
# GENERIC MODEL VALUE EXTRACTION
# ============================================================

IGNORED_MODEL_FIELDS = {
    "id",
    "pk",
    "service_id",
    "import_batch_id",
    "source_import_row_id",
    "import_row_id",
    "created_by_id",
    "verified_by_id",
    "created_at",
    "updated_at",
    "processed_at",
    "last_verified_at",
    "last_checked_at",
}


def model_business_values(
    obj,
):

    values = []

    urls = []


    for field in obj._meta.fields:

        name = field.name

        if name in IGNORED_MODEL_FIELDS:
            continue

        # Technical foreign keys are not business content.
        if isinstance(
            field,
            models.ForeignKey,
        ):
            continue

        try:

            value = getattr(
                obj,
                name,
            )

        except Exception:
            continue

        if value is None:
            continue

        if (
            isinstance(
                value,
                str,
            )
            and not value.strip()
        ):
            continue


        if isinstance(
            field,
            models.URLField,
        ):

            url = normalize_url(
                value
            )

            if url:
                urls.append(
                    url
                )

            continue


        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):

            for item in value:

                normalized = normalize_text(
                    item
                )

                if normalized:
                    values.append(
                        normalized
                    )

            continue


        if isinstance(
            value,
            dict,
        ):

            for key, item in value.items():

                key_text = normalize_text(
                    key
                )

                item_text = normalize_text(
                    item
                )

                if key_text:
                    values.append(
                        key_text
                    )

                if item_text:
                    values.append(
                        item_text
                    )

            continue


        normalized = normalize_text(
            value
        )

        if normalized:

            values.append(
                normalized
            )


    return {
        "texts":
            values,

        "urls":
            urls,
    }


# ============================================================
# SERVICE BUSINESS SNAPSHOT
# ============================================================

RELATED_MANAGERS = (
    "content_sections",
    "eligibility_rules",
    "document_requirements",
    "process_steps",
    "commercial_terms",
    "sources",
    "knowledge_sections",
    "comparison_entries",
)


def service_snapshot(
    service,
):

    base = model_business_values(
        service
    )

    texts = list(
        base["texts"]
    )

    urls = list(
        base["urls"]
    )

    related = {}


    for manager_name in RELATED_MANAGERS:

        manager = getattr(
            service,
            manager_name,
            None,
        )

        if manager is None:
            continue

        try:

            objects = list(
                manager.all()
            )

        except Exception:
            continue

        related_values = []

        related_urls = []


        for obj in objects:

            extracted = (
                model_business_values(
                    obj
                )
            )

            related_values.extend(
                extracted[
                    "texts"
                ]
            )

            related_urls.extend(
                extracted[
                    "urls"
                ]
            )


        related[
            manager_name
        ] = {
            "texts":
                related_values,

            "urls":
                related_urls,
        }

        texts.extend(
            related_values
        )

        urls.extend(
            related_urls
        )


    return {
        "service_id":
            service.pk,

        "service_code":
            service.service_id,

        "title":
            service.title,

        "texts":
            list(
                dict.fromkeys(
                    item
                    for item in texts
                    if item
                )
            ),

        "urls":
            list(
                dict.fromkeys(
                    item
                    for item in urls
                    if item
                )
            ),

        "related":
            related,
    }


# ============================================================
# MATCH HELPERS
# ============================================================

def text_exists(
    incoming,
    existing_values,
):

    needle = normalize_text(
        incoming
    )

    if not needle:
        return True


    for value in existing_values:

        existing = normalize_text(
            value
        )

        if not existing:
            continue


        if needle == existing:
            return True


        # Imported materialisation may combine multiple cells
        # into one paragraph. Accept containment when meaningful.
        if (
            len(needle) >= 12
            and needle in existing
        ):

            return True


        if (
            len(existing) >= 12
            and existing in needle
            and len(existing)
            / max(
                len(needle),
                1,
            )
            >= 0.80
        ):

            return True


    return False


def url_exists(
    incoming,
    existing_urls,
):

    needle = normalize_url(
        incoming
    )

    if not needle:
        return True

    return needle in {
        normalize_url(
            value
        )
        for value
        in existing_urls
        if value
    }


# ============================================================
# FIELD-SPECIFIC BUSINESS BUCKETS
# ============================================================

def related_texts(
    snapshot,
    manager_names,
):

    values = []

    for name in manager_names:

        values.extend(
            snapshot[
                "related"
            ].get(
                name,
                {},
            ).get(
                "texts",
                [],
            )
        )

    return values


def field_bucket(
    service,
    snapshot,
    field_name,
):

    field_name = str(
        field_name or ""
    ).lower()


    core_map = {

        "benefits": (
            "benefits",
        ),

        "eligibility": (
            "eligibility_summary",
            "applicable_for_raw",
        ),

        "applicable_for": (
            "applicable_for_raw",
        ),

        "deadline": (
            "application_deadline_raw",
            "estimated_processing_time",
        ),

        "funding_organisation": (
            "funding_organisation",
        ),

        "funding_type": (
            "funding_type",
        ),

        "scheme_type": (
            "funding_type",
        ),

        "focus_sectors": (
            "industries",
        ),

        "additional_info": (
            "important_notes",
            "internal_notes",
        ),

        "commercial_remark": (
            "pricing_notes",
            "important_notes",
        ),
    }


    manager_map = {

        "benefits": (
            "content_sections",
        ),

        "eligibility": (
            "eligibility_rules",
            "content_sections",
        ),

        "applicable_for": (
            "eligibility_rules",
            "content_sections",
        ),

        "deadline": (
            "content_sections",
        ),

        "funding_organisation": (
            "content_sections",
        ),

        "funding_type": (
            "content_sections",
        ),

        "scheme_type": (
            "content_sections",
        ),

        "focus_sectors": (
            "content_sections",
        ),

        "minimum_charge": (
            "commercial_terms",
        ),

        "government_charge": (
            "commercial_terms",
        ),

        "government_fee": (
            "commercial_terms",
        ),

        "vendor_cost": (
            "commercial_terms",
        ),

        "bdm_deduction": (
            "commercial_terms",
        ),

        "commercial_remark": (
            "commercial_terms",
            "content_sections",
        ),
    }


    values = []


    for attr in core_map.get(
        field_name,
        (),
    ):

        if not hasattr(
            service,
            attr,
        ):
            continue

        value = getattr(
            service,
            attr,
        )

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):

            values.extend(
                normalize_text(
                    item
                )
                for item in value
                if normalize_text(
                    item
                )
            )

        else:

            normalized = (
                normalize_text(
                    value
                )
            )

            if normalized:
                values.append(
                    normalized
                )


    values.extend(
        related_texts(
            snapshot,
            manager_map.get(
                field_name,
                (),
            ),
        )
    )


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Known structured fields must NOT fall back to arbitrary
    # Service text.
    #
    # If Food Future has no existing eligibility data, incoming
    # eligibility is a SAFE_ADDITION — it is not a replacement
    # just because the Service title/status exists.
    #
    # Only genuinely unknown fields use the global business
    # snapshot as a final deduplication bucket.
    # --------------------------------------------------------

    known_fields = (
        set(
            core_map.keys()
        )
        | set(
            manager_map.keys()
        )
    )

    if (
        not values
        and field_name
        not in known_fields
    ):

        values = list(
            snapshot[
                "texts"
            ]
        )


    return list(
        dict.fromkeys(
            value
            for value in values
            if value
        )
    )


# ============================================================
# STRUCTURED CANDIDATE DELTA
# ============================================================

URL_FIELDS = {
    "portal_link",
    "flyer",
    "application_link",
    "official_link",
    "reference_link",
}


SOURCE_KINDS_BY_FIELD = {

    "portal_link": {
        "APPLICATION",
        "OFFICIAL_PORTAL",
    },

    "application_link": {
        "APPLICATION",
    },

    "official_link": {
        "OFFICIAL_PORTAL",
    },

    "flyer": {
        "FLYER",
    },

    "reference_link": {
        "REFERENCE",
    },

    "additional_info": {
        "REFERENCE",
    },
}


def candidate_reference_url(
    value,
):

    """
    Convert only genuine URL-like values into URLs.

    Examples:
    https://example.com     -> URL
    tdf.drdo.gov.in         -> URL
    www.example.com         -> URL

    MEDTECH                 -> NOT a URL
    Wipro Foundation        -> NOT a URL
    Google grant            -> NOT a URL
    """

    value = str(
        value or ""
    ).strip()

    if not value:
        return ""


    lower = value.lower()


    if lower.startswith(
        (
            "http://",
            "https://",
        )
    ):

        return normalize_url(
            value
        )


    # Domain-like text without an explicit scheme.
    if (
        " " not in value
        and re.match(
            r"^(?:www\.)?"
            r"[a-z0-9]"
            r"[a-z0-9.-]*"
            r"\.[a-z]{2,}"
            r"(?:[/:?#].*)?$",
            lower,
        )
    ):

        return normalize_url(
            "https://"
            + value
        )


    return ""


def existing_source_urls_for_field(
    service,
    field_name,
):

    kinds = (
        SOURCE_KINDS_BY_FIELD.get(
            str(
                field_name or ""
            ).lower(),
            set(),
        )
    )

    if not kinds:

        return []


    manager = getattr(
        service,
        "sources",
        None,
    )

    if manager is None:

        return []


    urls = []


    try:

        sources = manager.all()

    except Exception:

        return []


    for source in sources:

        if (
            getattr(
                source,
                "source_kind",
                "",
            )
            not in kinds
        ):

            continue


        url = normalize_url(
            getattr(
                source,
                "source_url",
                "",
            )
        )

        if url:

            urls.append(
                url
            )


    return list(
        dict.fromkeys(
            urls
        )
    )


def compare_structured_candidate(
    service,
    candidate,
):

    snapshot = service_snapshot(
        service
    )

    differences = []


    fields = (
        candidate.get(
            "fields",
            {}
        )
        if isinstance(
            candidate.get(
                "fields",
                {},
            ),
            dict,
        )
        else {}
    )


    candidate_links = {}


    for item in (
        candidate.get(
            "links",
            []
        )
        or []
    ):

        if not isinstance(
            item,
            dict,
        ):

            continue

        field = str(
            item.get(
                "field",
                "",
            )
            or ""
        ).strip()

        url = normalize_url(
            item.get(
                "url"
            )
        )


        if (
            field
            and url
        ):

            candidate_links[
                field
            ] = url


    for field_name, value in fields.items():

        if field_name in {
            "scheme_name",
            "service_name",
            "title",
        }:
            continue

        if value is None:
            continue

        if (
            isinstance(
                value,
                str,
            )
            and not value.strip()
        ):
            continue


        # ----------------------------------------------------
        # SOURCE / LINK FIELDS
        #
        # Excel cells frequently contain a human-readable label:
        #
        #   MEDTECH
        #   Wipro Foundation
        #   Google grant
        #
        # while the real hyperlink lives in the cell hyperlink.
        #
        # Never compare those labels with Service URLs.
        # ----------------------------------------------------

        if field_name in URL_FIELDS:

            # When Excel supplied a real hyperlink, it is handled
            # once in the dedicated links loop below.
            if field_name in candidate_links:

                continue


            incoming_url = (
                candidate_reference_url(
                    value
                )
            )


            # Not a URL at all — this is only a display label.
            if not incoming_url:

                continue


            if url_exists(
                incoming_url,
                snapshot[
                    "urls"
                ],
            ):

                continue


            existing_same_kind = (
                existing_source_urls_for_field(
                    service,
                    field_name,
                )
            )


            differences.append(
                {
                    "field":
                        field_name,

                    "incoming":
                        incoming_url,

                    "change_type":
                        (
                            "SAFE_ADDITION"
                            if not existing_same_kind
                            else "CHANGED_INFORMATION"
                        ),
                }
            )

            continue


        # A URL can occasionally appear in another ordinary field.
        incoming_url = (
            candidate_reference_url(
                value
            )
        )


        if incoming_url:

            if not url_exists(
                incoming_url,
                snapshot[
                    "urls"
                ],
            ):

                differences.append(
                    {
                        "field":
                            field_name,

                        "incoming":
                            incoming_url,

                        "change_type":
                            "SAFE_ADDITION",
                    }
                )

            continue


        bucket = field_bucket(
            service,
            snapshot,
            field_name,
        )


        if text_exists(
            value,
            bucket,
        ):

            continue


        differences.append(
            {
                "field":
                    field_name,

                "incoming":
                    value,

                "change_type":
                    (
                        "SAFE_ADDITION"
                        if not bucket
                        else "CHANGED_INFORMATION"
                    ),
            }
        )


    # Links extracted from cell hyperlinks are also business data.
    for link in (
        candidate.get(
            "links",
            []
        )
        or []
    ):

        if not isinstance(
            link,
            dict,
        ):
            continue

        field_name = (
            link.get(
                "field"
            )
            or "link"
        )

        url = normalize_url(
            link.get(
                "url"
            )
        )


        if not url:

            continue


        # URL is already present anywhere on the Service.
        if url_exists(
            url,
            snapshot[
                "urls"
            ],
        ):

            continue


        existing_same_kind = (
            existing_source_urls_for_field(
                service,
                field_name,
            )
        )


        differences.append(
            {
                "field":
                    field_name,

                "incoming":
                    url,

                "change_type":
                    (
                        "SAFE_ADDITION"
                        if not existing_same_kind
                        else "CHANGED_INFORMATION"
                    ),
            }
        )


    return differences


# ============================================================
# NARRATIVE KNOWLEDGE DELTA
# ============================================================

GENERIC_HEADINGS = {
    "benefits",
    "eligibility",
    "documents",
    "documents required",
    "commercials",
    "commercial",
    "please note",
    "process",
    "scope of work",
    "descriptive scope of work",
}


def compare_narrative_candidate(
    service,
    candidate,
):

    snapshot = service_snapshot(
        service
    )

    differences = []


    sections = (
        candidate.get(
            "sections",
            []
        )
        or []
    )


    for section in sections:

        if not isinstance(
            section,
            dict,
        ):
            continue

        content = str(
            section.get(
                "content",
                "",
            )
            or ""
        ).strip()

        if not content:
            continue


        clean = normalize_text(
            content
        )

        if (
            section.get(
                "is_heading"
            )
            and clean
            in GENERIC_HEADINGS
        ):
            continue


        # ----------------------------------------------------
        # GLOBAL BUSINESS-KNOWLEDGE DEDUPLICATION
        #
        # A source paragraph may be classified under a slightly
        # different section on a later ingestion run.
        #
        # Example:
        # source says FUNDING
        # existing Toolkit stored it under NOTES/OTHER.
        #
        # If the exact business information already exists
        # anywhere on this Service, it is NOT a change.
        # ----------------------------------------------------

        if text_exists(
            content,
            snapshot[
                "texts"
            ],
        ):

            url = section.get(
                "url"
            )

            # Existing text + no new link = fully unchanged.
            if (
                not url
                or url_exists(
                    url,
                    snapshot[
                        "urls"
                    ],
                )
            ):

                continue


        section_type = str(
            section.get(
                "section_type",
                "OTHER",
            )
            or "OTHER"
        ).upper()


        manager_values = list(
            snapshot[
                "texts"
            ]
        )


        if section_type == "ELIGIBILITY":

            manager_values = (
                related_texts(
                    snapshot,
                    (
                        "eligibility_rules",
                        "content_sections",
                    ),
                )
                or manager_values
            )


        elif section_type == "PROCESS":

            manager_values = (
                related_texts(
                    snapshot,
                    (
                        "process_steps",
                        "content_sections",
                    ),
                )
                or manager_values
            )


        elif section_type == "DOCUMENTS":

            manager_values = (
                related_texts(
                    snapshot,
                    (
                        "document_requirements",
                        "content_sections",
                    ),
                )
                or manager_values
            )


        elif section_type == "COMMERCIAL":

            manager_values = (
                related_texts(
                    snapshot,
                    (
                        "commercial_terms",
                        "content_sections",
                    ),
                )
                or manager_values
            )


        elif section_type in {
            "BENEFITS",
            "FUNDING",
            "SCOPE",
            "TIMELINE",
            "NOTES",
            "OVERVIEW",
            "OTHER",
        }:

            manager_values = (
                related_texts(
                    snapshot,
                    (
                        "content_sections",
                    ),
                )
                or manager_values
            )


        if text_exists(
            content,
            manager_values,
        ):
            continue


        differences.append(
            {
                "field":
                    (
                        f"section:"
                        f"{section_type}"
                    ),

                "incoming":
                    content,

                "source_row":
                    section.get(
                        "source_row"
                    ),

                "change_type":
                    (
                        "SAFE_ADDITION"
                        if not manager_values
                        else "CHANGED_INFORMATION"
                    ),
            }
        )


        url = section.get(
            "url"
        )

        if (
            url
            and not url_exists(
                url,
                snapshot[
                    "urls"
                ],
            )
        ):

            differences.append(
                {
                    "field":
                        (
                            f"link:"
                            f"{section_type}"
                        ),

                    "incoming":
                        url,

                    "source_row":
                        section.get(
                            "source_row"
                        ),

                    "change_type":
                        (
                            "SAFE_ADDITION"
                            if not snapshot[
                                "urls"
                            ]
                            else "CHANGED_INFORMATION"
                        ),
                }
            )


    return differences


# ============================================================
# CANDIDATE CLASSIFICATION
# ============================================================

def classify_candidate(
    candidate,
):

    match = (
        candidate.get(
            "match",
            {}
        )
        or {}
    )

    action = match.get(
        "action"
    )

    service_id = match.get(
        "matched_service_id"
    )


    if (
        action == "INVALID"
    ):

        return {
            "status":
                "CONFLICT",

            "reason":
                "Candidate title is invalid.",

            "differences":
                [],
        }


    if (
        action == "MERGE_REVIEW"
    ):

        return {
            "status":
                "CONFLICT",

            "reason":
                "Possible existing Service requires review.",

            "matched_service_id":
                service_id,

            "differences":
                [],
        }


    if (
        action == "CREATE"
        or not service_id
    ):

        return {
            "status":
                "NEW_SERVICE",

            "reason":
                "No reliable existing Service match.",

            "differences":
                [],
        }


    service = (
        Service.objects
        .filter(
            pk=service_id
        )
        .first()
    )


    if service is None:

        return {
            "status":
                "CONFLICT",

            "reason":
                "Matched Service no longer exists.",

            "differences":
                [],
        }


    if candidate.get(
        "sections"
    ):

        differences = (
            compare_narrative_candidate(
                service,
                candidate,
            )
        )

    else:

        differences = (
            compare_structured_candidate(
                service,
                candidate,
            )
        )


    if not differences:

        status = (
            "NO_CHANGE"
        )

    elif any(
        item[
            "change_type"
        ]
        == "CHANGED_INFORMATION"
        for item in differences
    ):

        status = (
            "CHANGED_INFORMATION"
        )

    else:

        status = (
            "SAFE_ADDITION"
        )


    return {
        "status":
            status,

        "matched_service_id":
            service.pk,

        "matched_service_code":
            service.service_id,

        "matched_service_title":
            service.title,

        "differences":
            differences,
    }


# ============================================================
# WHOLE FILE PREVIEW
# ============================================================

def build_delta_preview(
    file_obj,
    filename,
    *,
    force_compare=False,
):

    file_obj.seek(
        0
    )

    source_bytes = (
        file_obj.read()
    )

    file_obj.seek(
        0
    )


    digest = hashlib.sha256(
        source_bytes
    ).hexdigest()


    duplicate_batch = (
        ImportBatch.objects
        .filter(
            file_sha256=digest,
            status="IMPORTED",
        )
        .order_by(
            "-imported_at",
            "-created_at",
        )
        .first()
    )


    if (
        duplicate_batch
        and not force_compare
    ):

        return {
            "filename":
                filename,

            "sha256":
                digest,

            "duplicate_source":
                True,

            "duplicate_of_batch_id":
                duplicate_batch.pk,

            "candidate_count":
                0,

            "change_candidate_count":
                0,

            "status_counts":
                {
                    "NO_CHANGE":
                        0,

                    "SAFE_ADDITION":
                        0,

                    "CHANGED_INFORMATION":
                        0,

                    "CONFLICT":
                        0,

                    "NEW_SERVICE":
                        0,
                },

            "items":
                [],
        }


    analysis = analyse_file(
        file_obj,
        filename,
    )


    items = []

    counts = Counter()


    for sheet in analysis.get(
        "sheets",
        []
    ):

        sheet_name = sheet.get(
            "name"
        )

        sheet_kind = sheet.get(
            "kind"
        )


        for candidate in (
            sheet.get(
                "candidates",
                []
            )
            or []
        ):

            result = classify_candidate(
                candidate
            )

            status = result[
                "status"
            ]

            counts[
                status
            ] += 1


            items.append(
                {
                    "sheet_name":
                        sheet_name,

                    "sheet_kind":
                        sheet_kind,

                    "source_row":
                        candidate.get(
                            "source_row"
                        ),

                    "title":
                        candidate.get(
                            "title"
                        ),

                    "match":
                        candidate.get(
                            "match"
                        ),

                    **result,
                }
            )


    change_statuses = {
        "SAFE_ADDITION",
        "CHANGED_INFORMATION",
        "CONFLICT",
        "NEW_SERVICE",
    }


    change_candidate_count = sum(
        1
        for item in items
        if item[
            "status"
        ]
        in change_statuses
    )


    return {
        "filename":
            filename,

        "sha256":
            digest,

        "duplicate_source":
            False,

        "duplicate_of_batch_id":
            (
                duplicate_batch.pk
                if duplicate_batch
                else None
            ),

        "candidate_count":
            len(
                items
            ),

        "change_candidate_count":
            change_candidate_count,

        "status_counts":
            {
                "NO_CHANGE":
                    counts[
                        "NO_CHANGE"
                    ],

                "SAFE_ADDITION":
                    counts[
                        "SAFE_ADDITION"
                    ],

                "CHANGED_INFORMATION":
                    counts[
                        "CHANGED_INFORMATION"
                    ],

                "CONFLICT":
                    counts[
                        "CONFLICT"
                    ],

                "NEW_SERVICE":
                    counts[
                        "NEW_SERVICE"
                    ],
            },

        "items":
            items,
    }
