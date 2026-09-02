"""
BharatNXT Wave workbook transformation engine.

STEP 11A scope:
- exact source / contract verification
- final 162-Service planning
- 8 planned Category creations
- deterministic primary domain/category/service_kind
- secondary ServiceClassification planning
- 161 ServiceCommercial plans
- model-aware validation

IMPORTANT:
This module PLANS transformations only.
It does not perform database writes.
"""

import hashlib
import json
import re

from collections import Counter, defaultdict
from pathlib import Path

from django.utils.text import slugify

from toolkit.models import (
    Category,
    ImportBatch,
    ImportRow,
    Service,
    ServiceCommercial,
    ServiceDomain,
)


# ============================================================
# CONTRACT / SOURCE CONSTANTS
# ============================================================

BATCH_ID = 5

EXPECTED_SOURCE_SHA256 = (
    "4228c2dadda12e220617acba7e301f809"
    "edf0dec42fc98983b1aef934287744d"
)

CONTRACT_PATH = Path(
    "confidential_source/audit/"
    "step10_mapping_contract_v3.json"
)

EXPECTED_CONTRACT_SHA256 = (
    "a3cb9e17122be51c5625f00bb00580249806"
    "c5d60c44b634a677282e72650dd6"
)

EXPECTED_STAGED_ROWS = 478

EXPECTED_STRUCTURED = 100

EXPECTED_COMMERCIAL_IDENTITIES = 61

EXPECTED_COMMERCIAL_ADDITIONAL = 60

EXPECTED_ROLLING_NEW = 2

EXPECTED_FINAL_SERVICES = 162

EXPECTED_STRUCTURED_COMMERCIAL = 99

EXPECTED_AMOUNT_COMMERCIAL_ROWS = 62

EXPECTED_COMMERCIAL_RECORDS = 161


# ============================================================
# DOMAIN CONSTANTS
# ============================================================

DOMAIN_BUSINESS = (
    "business-incorporation-and-launch"
)

DOMAIN_COMPLIANCE = (
    "compliance-management"
)

DOMAIN_LICENSES = (
    "licenses-registrations-and-certifications"
)

DOMAIN_GOVT = (
    "government-schemes-and-grants"
)

DOMAIN_FUNDING = (
    "funding-and-equity-support"
)

DOMAIN_LEGAL = (
    "legal-drafting-and-contracts"
)

DOMAIN_DIGITAL = (
    "branding-website-and-digital-presence"
)

DOMAIN_STRATEGY = (
    "business-strategy-and-growth-consulting"
)


# ============================================================
# CATEGORY CONSTANTS
# ============================================================

CAT_COMPANY_INCORPORATION = (
    "company-incorporation"
)

CAT_BUSINESS_REGISTRATIONS = (
    "business-registrations"
)

CAT_STARTUP_MSME = (
    "startup-and-msme-recognition"
)

CAT_ANNUAL_ROC = (
    "annual-and-roc-compliance"
)

CAT_GST_TAX = (
    "gst-and-tax-compliance"
)

CAT_LABOUR = (
    "labour-law-compliance"
)

CAT_AUDIT = (
    "audit-and-reporting"
)

CAT_GOVT_GRANTS = (
    "government-grants"
)

CAT_CREDIT = (
    "credit-and-guarantee-schemes"
)

CAT_SECTOR_SCHEMES = (
    "sector-specific-schemes"
)

CAT_SUBSIDIES = (
    "state-subsidies"
)

CAT_LICENSES = (
    "licenses"
)

CAT_CERTIFICATIONS = (
    "certifications"
)

CAT_IP = (
    "trademark-and-intellectual-property"
)

CAT_TRADE_REG = (
    "trade-and-business-registrations"
)

CAT_INVESTOR = (
    "investor-connect"
)

CAT_PITCH = (
    "pitch-deck-and-financial-model"
)

CAT_VALUATION = (
    "valuation"
)

CAT_DATA_ROOM = (
    "data-room-and-fundraise-readiness"
)

CAT_FOUNDER_AGREEMENTS = (
    "founder-agreements"
)

CAT_NDA = (
    "ndas-and-commercial-contracts"
)

CAT_VENDOR_AGREEMENTS = (
    "vendor-and-partnership-agreements"
)

CAT_HR_POLICIES = (
    "hr-and-employment-policies"
)

CAT_BRANDING = (
    "branding-and-identity"
)

CAT_WEBSITE = (
    "website-development"
)

CAT_DIGITAL_MARKETING = (
    "digital-marketing"
)

CAT_SOCIAL = (
    "social-media"
)

CAT_SEO = (
    "seo"
)

CAT_HIRING = (
    "hiring-and-hr-systems"
)

CAT_PRICING = (
    "pricing-strategy"
)

CAT_GTM = (
    "go-to-market-strategy"
)

CAT_SCALING = (
    "scaling-and-growth"
)


# ============================================================
# NEW CATEGORY PLAN
# ============================================================

NEW_CATEGORY_PLAN = (
    {
        "name": "Agriculture Schemes",
        "slug": "agriculture-schemes",
        "domain_slug": DOMAIN_GOVT,
        "display_order": 5,
    },
    {
        "name": "NGO-Focused Schemes",
        "slug": "ngo-focused-schemes",
        "domain_slug": DOMAIN_GOVT,
        "display_order": 6,
    },
    {
        "name": "Women-Focused Schemes",
        "slug": "women-focused-schemes",
        "domain_slug": DOMAIN_GOVT,
        "display_order": 7,
    },
    {
        "name": "Equity Funding",
        "slug": "equity-funding",
        "domain_slug": DOMAIN_FUNDING,
        "display_order": 5,
    },
    {
        "name": "Debt Funding",
        "slug": "debt-funding",
        "domain_slug": DOMAIN_FUNDING,
        "display_order": 6,
    },
    {
        "name": "Funding Programs",
        "slug": "funding-programs",
        "domain_slug": DOMAIN_FUNDING,
        "display_order": 7,
    },
    {
        "name": "Mixed Finance",
        "slug": "mixed-finance",
        "domain_slug": DOMAIN_FUNDING,
        "display_order": 8,
    },
    {
        "name": "Other Business Services",
        "slug": "other-business-services",
        "domain_slug": DOMAIN_STRATEGY,
        "display_order": 5,
    },
)


# ============================================================
# STRUCTURED SERVICE KIND LOGIC
# ============================================================

SOURCE_TYPE_KEYWORDS = {
    "GRANT": (
        "grant",
    ),
    "LOAN": (
        "loan",
    ),
    "DEBT": (
        "debt",
    ),
    "EQUITY": (
        "equity",
    ),
    "SUBSIDY": (
        "subsidy",
    ),
    "CERTIFICATION": (
        "certificate",
        "certification",
    ),
    "GOVT_SCHEME": (
        "government scheme",
        "govt scheme",
    ),
    "REGISTRATION": (
        "registration",
    ),
    "COMPLIANCE": (
        "compliance",
    ),
    "LEGAL": (
        "legal",
    ),
    "CONSULTING": (
        "consulting",
        "consultancy",
    ),
    "DIGITAL": (
        "digital",
    ),
}


SHEET_PRIMARY_KIND = {
    "GRANT": "GRANT",
    "Women_GRANT": "GRANT",
    "Agriculture_FUND": "GOVT_SCHEME",
    "NGO_GRANT": "GRANT",
    "EQUITY": "EQUITY",
    "GRANTDEBTEQUITY": "GOVT_SCHEME",
    "DEBTEQUITY": "GOVT_SCHEME",
    "LOAN ONLY": "LOAN",
    "LOANSUBSIDY": "GOVT_SCHEME",
    "CERTGEM": "CERTIFICATION",
}


STRUCTURED_PRIMARY_MAP = {
    "CERTIFICATION": (
        DOMAIN_LICENSES,
        CAT_CERTIFICATIONS,
    ),
    "EQUITY": (
        DOMAIN_FUNDING,
        "equity-funding",
    ),
    "GOVT_SCHEME": (
        DOMAIN_GOVT,
        CAT_SECTOR_SCHEMES,
    ),
    "GRANT": (
        DOMAIN_GOVT,
        CAT_GOVT_GRANTS,
    ),
    "LOAN": (
        DOMAIN_GOVT,
        CAT_CREDIT,
    ),
    "SUBSIDY": (
        DOMAIN_GOVT,
        CAT_SUBSIDIES,
    ),
    "DEBT": (
        DOMAIN_FUNDING,
        "debt-funding",
    ),
}


# ============================================================
# STRUCTURED CLASSIFICATIONS
# ============================================================

SOURCE_SHEET_CLASSIFICATIONS = {
    "GRANT": (
        "Grant",
    ),
    "Women_GRANT": (
        "Grant",
        "Women",
    ),
    "Agriculture_FUND": (
        "Agriculture",
        "Funding",
    ),
    "NGO_GRANT": (
        "Grant",
        "NGO",
    ),
    "EQUITY": (
        "Equity",
    ),
    "GRANTDEBTEQUITY": (
        "Grant",
        "Debt",
        "Equity",
        "Mixed Finance",
    ),
    "DEBTEQUITY": (
        "Debt",
        "Equity",
        "Mixed Finance",
    ),
    "LOAN ONLY": (
        "Loan",
    ),
    "LOANSUBSIDY": (
        "Loan",
        "Subsidy",
        "Mixed Finance",
    ),
    "CERTGEM": (
        "Certification",
    ),
}


CLASSIFICATION_CATEGORY = {
    "Grant": (
        DOMAIN_GOVT,
        CAT_GOVT_GRANTS,
    ),
    "Loan": (
        DOMAIN_GOVT,
        CAT_CREDIT,
    ),
    "Subsidy": (
        DOMAIN_GOVT,
        CAT_SUBSIDIES,
    ),
    "Certification": (
        DOMAIN_LICENSES,
        CAT_CERTIFICATIONS,
    ),
    "Agriculture": (
        DOMAIN_GOVT,
        "agriculture-schemes",
    ),
    "Debt": (
        DOMAIN_FUNDING,
        "debt-funding",
    ),
    "Equity": (
        DOMAIN_FUNDING,
        "equity-funding",
    ),
    "Funding": (
        DOMAIN_FUNDING,
        "funding-programs",
    ),
    "Mixed Finance": (
        DOMAIN_FUNDING,
        "mixed-finance",
    ),
    "NGO": (
        DOMAIN_GOVT,
        "ngo-focused-schemes",
    ),
    "Women": (
        DOMAIN_GOVT,
        "women-focused-schemes",
    ),
}


KIND_CLASSIFICATION = {
    "GRANT": "Grant",
    "LOAN": "Loan",
    "DEBT": "Debt",
    "EQUITY": "Equity",
    "SUBSIDY": "Subsidy",
    "CERTIFICATION": "Certification",
}


# ============================================================
# COMMERCIAL KIND / CATEGORY RULES
# ============================================================

COMMERCIAL_KIND_RULES = {
    "REGISTRATION": (
        "registration",
        "incorporation",
        "register",
    ),
    "CERTIFICATION": (
        "certification",
        "certificate",
        "iso",
        "cert",
    ),
}


COMMERCIAL_CATEGORY_RULES = (
    (
        DOMAIN_LICENSES,
        CAT_IP,
        (
            "trademark",
            "trade mark",
            "patent",
            "copyright",
            "intellectual property",
        ),
    ),
    (
        DOMAIN_COMPLIANCE,
        CAT_GST_TAX,
        (
            "gst",
            "income tax",
            "tax return",
            "tds",
        ),
    ),
    (
        DOMAIN_COMPLIANCE,
        CAT_ANNUAL_ROC,
        (
            "roc",
            "annual filing",
            "annual compliance",
            "mca filing",
        ),
    ),
    (
        DOMAIN_COMPLIANCE,
        CAT_LABOUR,
        (
            "labour",
            "labor",
            "pf",
            "provident fund",
            "esi",
            "esic",
        ),
    ),
    (
        DOMAIN_COMPLIANCE,
        CAT_AUDIT,
        (
            "audit",
            "reporting",
        ),
    ),
    (
        DOMAIN_LICENSES,
        CAT_CERTIFICATIONS,
        (
            "iso",
            "certificate",
            "certification",
            "cert",
        ),
    ),
    (
        DOMAIN_LICENSES,
        CAT_LICENSES,
        (
            "license",
            "licence",
        ),
    ),
    (
        DOMAIN_BUSINESS,
        CAT_COMPANY_INCORPORATION,
        (
            "private limited",
            "pvt ltd",
            "incorporation",
            "company formation",
            "opc",
            "one person company",
            "llp",
            "limited liability partnership",
        ),
    ),
    (
        DOMAIN_BUSINESS,
        CAT_STARTUP_MSME,
        (
            "startup india",
            "start up india",
            "msme",
            "udyam",
        ),
    ),
    (
        DOMAIN_LICENSES,
        CAT_TRADE_REG,
        (
            "trade registration",
            "trade licence",
            "trade license",
            "gem",
            "import export",
            "iec",
        ),
    ),
    (
        DOMAIN_FUNDING,
        CAT_PITCH,
        (
            "pitch deck",
            "financial model",
        ),
    ),
    (
        DOMAIN_FUNDING,
        CAT_VALUATION,
        (
            "valuation",
        ),
    ),
    (
        DOMAIN_FUNDING,
        CAT_DATA_ROOM,
        (
            "data room",
            "fundraise readiness",
        ),
    ),
    (
        DOMAIN_FUNDING,
        CAT_INVESTOR,
        (
            "investor",
            "fundraise",
            "fund raising",
            "fundraising",
        ),
    ),
    (
        DOMAIN_GOVT,
        CAT_GOVT_GRANTS,
        (
            "grant",
        ),
    ),
    (
        DOMAIN_GOVT,
        CAT_CREDIT,
        (
            "loan",
            "credit guarantee",
        ),
    ),
    (
        DOMAIN_GOVT,
        CAT_SUBSIDIES,
        (
            "subsidy",
        ),
    ),
    (
        DOMAIN_LEGAL,
        CAT_FOUNDER_AGREEMENTS,
        (
            "founder agreement",
            "founders agreement",
        ),
    ),
    (
        DOMAIN_LEGAL,
        CAT_NDA,
        (
            "nda",
            "non disclosure",
            "commercial contract",
        ),
    ),
    (
        DOMAIN_LEGAL,
        CAT_VENDOR_AGREEMENTS,
        (
            "vendor agreement",
            "partnership agreement",
        ),
    ),
    (
        DOMAIN_LEGAL,
        CAT_HR_POLICIES,
        (
            "employment agreement",
            "employment policy",
            "hr policy",
        ),
    ),
    (
        DOMAIN_DIGITAL,
        CAT_SEO,
        (
            "seo",
            "search engine optimization",
        ),
    ),
    (
        DOMAIN_DIGITAL,
        CAT_SOCIAL,
        (
            "social media",
        ),
    ),
    (
        DOMAIN_DIGITAL,
        CAT_WEBSITE,
        (
            "website",
            "web development",
        ),
    ),
    (
        DOMAIN_DIGITAL,
        CAT_BRANDING,
        (
            "branding",
            "brand identity",
            "logo",
        ),
    ),
    (
        DOMAIN_DIGITAL,
        CAT_DIGITAL_MARKETING,
        (
            "digital marketing",
            "online marketing",
        ),
    ),
    (
        DOMAIN_STRATEGY,
        CAT_HIRING,
        (
            "hiring",
            "recruitment",
            "hr system",
        ),
    ),
    (
        DOMAIN_STRATEGY,
        CAT_PRICING,
        (
            "pricing strategy",
            "pricing",
        ),
    ),
    (
        DOMAIN_STRATEGY,
        CAT_GTM,
        (
            "go to market",
            "gtm",
        ),
    ),
    (
        DOMAIN_STRATEGY,
        CAT_SCALING,
        (
            "scaling",
            "growth strategy",
        ),
    ),
    (
        DOMAIN_BUSINESS,
        CAT_BUSINESS_REGISTRATIONS,
        (
            "registration",
            "register",
        ),
    ),
)


# ============================================================
# GENERIC HELPERS
# ============================================================

def sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
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


def normalize_identity(value):
    if value is None:
        return ""

    text = str(
        value
    ).casefold()

    text = text.replace(
        "&",
        " and ",
    )

    text = re.sub(
        r"[_/]+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def raw(row):
    return (
        row.raw_data
        if isinstance(
            row.raw_data,
            dict,
        )
        else {}
    )


def meta(row):
    value = raw(row).get(
        "_meta",
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def cells(row):
    value = raw(row).get(
        "cells",
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def fields(row):
    value = raw(row).get(
        "fields",
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def payload_value(payload):
    if not isinstance(
        payload,
        dict,
    ):
        return ""

    value = payload.get(
        "value"
    )

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def column_value(
    row,
    column,
):
    return payload_value(
        cells(row).get(
            column,
            {},
        )
    )


def has_phrase(
    identity,
    phrase,
):
    text = normalize_identity(
        identity
    )

    phrase = normalize_identity(
        phrase
    )

    if not text or not phrase:
        return False

    return bool(
        re.search(
            r"(?:^|\s)"
            + re.escape(
                phrase
            )
            + r"(?:\s|$)",
            text,
        )
    )


def has_any(
    identity,
    phrases,
):
    return any(
        has_phrase(
            identity,
            phrase,
        )
        for phrase in phrases
    )


def identity_hash(
    identity,
    length=12,
):
    return hashlib.sha256(
        identity.encode(
            "utf-8"
        )
    ).hexdigest()[
        :length
    ].upper()


def deterministic_service_id(
    identity
):
    return (
        "BNXT-SVC-"
        + identity_hash(
            identity,
            12,
        )
    )


def deterministic_slug(
    title,
    identity,
    used_slugs,
    max_length,
):
    base = slugify(
        title
    )

    if not base:
        base = (
            "service-"
            + identity_hash(
                identity,
                8,
            ).lower()
        )

    base = base[
        :max_length
    ].strip("-")

    candidate = base

    if (
        not candidate
        or candidate
        in used_slugs
    ):
        suffix = (
            "-"
            + identity_hash(
                identity,
                8,
            ).lower()
        )

        available = (
            max_length
            - len(suffix)
        )

        candidate = (
            base[:available]
            .rstrip("-")
            + suffix
        )

    if candidate in used_slugs:
        raise ValueError(
            "Deterministic slug collision "
            "could not be resolved."
        )

    used_slugs.add(
        candidate
    )

    return candidate


# ============================================================
# SOURCE TYPE RESOLUTION
# ============================================================

def source_type_signals(
    text
):
    normalized = normalize_identity(
        text
    )

    matches = set()

    for kind, terms in (
        SOURCE_TYPE_KEYWORDS.items()
    ):
        for term in terms:
            if has_phrase(
                normalized,
                term,
            ):
                matches.add(
                    kind
                )
                break

    return matches


def resolve_structured_kind(
    group,
    valid_service_kinds,
):
    sheets = {
        row.sheet_name
        for row in group
    }

    source_values = []

    for row in group:
        value = payload_value(
            fields(row).get(
                "scheme_type",
                {},
            )
        )

        if value:
            source_values.append(
                value
            )

    normalized_values = {
        normalize_identity(
            value
        )
        for value in source_values
        if normalize_identity(
            value
        )
    }

    signals = set()

    for value in source_values:
        signals.update(
            source_type_signals(
                value
            )
        )

    valid_signals = (
        signals
        & valid_service_kinds
    )

    if (
        len(valid_signals) == 1
        and len(
            normalized_values
        ) <= 1
    ):
        return next(
            iter(
                valid_signals
            )
        )

    sheet_kinds = {
        SHEET_PRIMARY_KIND[
            sheet
        ]
        for sheet in sheets
        if sheet in SHEET_PRIMARY_KIND
    }

    if len(sheet_kinds) == 1:
        return next(
            iter(
                sheet_kinds
            )
        )

    if sheet_kinds:
        return "GOVT_SCHEME"

    return None


# ============================================================
# COMMERCIAL RESOLUTION
# ============================================================

def resolve_commercial_kind(
    identity
):
    signals = set()

    for kind, terms in (
        COMMERCIAL_KIND_RULES.items()
    ):
        if has_any(
            identity,
            terms,
        ):
            signals.add(
                kind
            )

    if len(signals) == 1:
        return next(
            iter(
                signals
            )
        )

    return "OTHER"


def commercial_category_matches(
    identity
):
    matches = []

    for (
        domain_slug,
        category_slug,
        phrases,
    ) in COMMERCIAL_CATEGORY_RULES:

        if has_any(
            identity,
            phrases,
        ):
            pair = (
                domain_slug,
                category_slug,
            )

            if pair not in matches:
                matches.append(
                    pair
                )

    return matches


def resolve_commercial_primary(
    identity,
    kind,
):
    matches = (
        commercial_category_matches(
            identity
        )
    )

    if matches:
        return (
            matches[0],
            "TITLE_SIGNAL",
            matches,
        )

    if kind == "CERTIFICATION":
        pair = (
            DOMAIN_LICENSES,
            CAT_CERTIFICATIONS,
        )

        return (
            pair,
            "KIND_FALLBACK",
            [],
        )

    if kind == "REGISTRATION":
        pair = (
            DOMAIN_BUSINESS,
            CAT_BUSINESS_REGISTRATIONS,
        )

        return (
            pair,
            "KIND_FALLBACK",
            [],
        )

    return (
        (
            DOMAIN_STRATEGY,
            "other-business-services",
        ),
        "GENERIC_CATEGORY",
        [],
    )


# ============================================================
# CONTRACT / SOURCE LOAD
# ============================================================

def load_verified_context():
    if not CONTRACT_PATH.exists():
        raise RuntimeError(
            "Mapping Contract v3 is missing."
        )

    contract_hash = sha256_file(
        CONTRACT_PATH
    )

    if (
        contract_hash
        != EXPECTED_CONTRACT_SHA256
    ):
        raise RuntimeError(
            "Mapping Contract v3 SHA-256 changed."
        )

    contract = json.loads(
        CONTRACT_PATH.read_text(
            encoding="utf-8"
        )
    )

    if (
        contract.get(
            "contract",
            {},
        ).get(
            "version"
        )
        != 3
    ):
        raise RuntimeError(
            "Expected Mapping Contract version 3."
        )

    batch = ImportBatch.objects.get(
        pk=BATCH_ID
    )

    if (
        batch.file_sha256
        != EXPECTED_SOURCE_SHA256
    ):
        raise RuntimeError(
            "ImportBatch source hash changed."
        )

    batch_metadata = (
        batch.metadata
        if isinstance(
            batch.metadata,
            dict,
        )
        else {}
    )

    if (
        batch_metadata.get(
            "operation"
        )
        != "workbook_staging"
    ):
        raise RuntimeError(
            "ImportBatch #5 is not "
            "the approved staging batch."
        )

    staged_rows = list(
        ImportRow.objects
        .filter(
            import_batch=batch
        )
        .order_by(
            "sheet_name",
            "source_row_number",
            "id",
        )
    )

    if (
        len(staged_rows)
        != EXPECTED_STAGED_ROWS
    ):
        raise RuntimeError(
            "Expected 478 staged ImportRows."
        )

    return (
        contract,
        batch,
        staged_rows,
    )


# ============================================================
# MODEL VOCABULARY
# ============================================================

def model_vocabulary():
    service_kind_field = (
        Service._meta.get_field(
            "service_kind"
        )
    )

    status_field = (
        Service._meta.get_field(
            "status"
        )
    )

    priority_field = (
        Service._meta.get_field(
            "priority"
        )
    )

    service_kind_choices = {
        str(value)
        for value, label
        in service_kind_field.choices
    }

    status_choices = {
        str(value)
        for value, label
        in status_field.choices
    }

    priority_choices = {
        str(value)
        for value, label
        in priority_field.choices
    }

    return {
        "service_kind_choices":
            service_kind_choices,
        "status_choices":
            status_choices,
        "priority_choices":
            priority_choices,
    }


# ============================================================
# CATEGORY PLAN
# ============================================================

def build_category_plan():
    domains = {
        domain.slug: domain
        for domain in (
            ServiceDomain.objects.all()
        )
    }

    if len(domains) != 8:
        raise RuntimeError(
            "Expected 8 existing ServiceDomains."
        )

    existing_categories = {
        (
            category.domain.slug,
            category.slug,
        ): category
        for category in (
            Category.objects
            .select_related(
                "domain"
            )
            .all()
        )
    }

    if len(existing_categories) != 32:
        raise RuntimeError(
            "Expected 32 existing Categories."
        )

    create_plan = []

    available_pairs = set(
        existing_categories
    )

    for item in NEW_CATEGORY_PLAN:
        domain_slug = item[
            "domain_slug"
        ]

        if domain_slug not in domains:
            raise RuntimeError(
                "Planned Category references "
                "a missing domain."
            )

        pair = (
            domain_slug,
            item["slug"],
        )

        if pair in available_pairs:
            raise RuntimeError(
                "A planned new Category "
                "already exists unexpectedly."
            )

        create_plan.append(
            dict(item)
        )

        available_pairs.add(
            pair
        )

    if len(create_plan) != 8:
        raise RuntimeError(
            "Expected exactly 8 Category plans."
        )

    return {
        "domains": domains,
        "existing_categories":
            existing_categories,
        "create": create_plan,
        "available_pairs":
            available_pairs,
    }


# ============================================================
# BUILD FINAL SERVICE PLAN
# ============================================================

def build_services(
    staged_rows,
    category_context,
    vocabulary,
):
    valid_service_kinds = vocabulary[
        "service_kind_choices"
    ]

    if "DRAFT" not in (
        vocabulary[
            "status_choices"
        ]
    ):
        raise RuntimeError(
            "DRAFT Service status is unavailable."
        )

    if "NORMAL" not in (
        vocabulary[
            "priority_choices"
        ]
    ):
        raise RuntimeError(
            "NORMAL Service priority is unavailable."
        )

    # --------------------------------------------------------
    # Structured groups
    # --------------------------------------------------------

    structured_rows = [
        row
        for row in staged_rows
        if (
            meta(row).get(
                "family"
            )
            == "SCHEME_TABLE"
            and row.source_key
        )
    ]

    structured_groups = defaultdict(
        list
    )

    for row in structured_rows:
        title = payload_value(
            fields(row).get(
                "scheme_name",
                {},
            )
        )

        identity = normalize_identity(
            title
        )

        if identity:
            structured_groups[
                identity
            ].append(
                row
            )

    if (
        len(structured_groups)
        != EXPECTED_STRUCTURED
    ):
        raise RuntimeError(
            "Expected 100 structured identities."
        )

    # --------------------------------------------------------
    # Commercial catalogue
    # --------------------------------------------------------

    amount_rows = [
        row
        for row in staged_rows
        if (
            row.sheet_name
            == "AMOUNT DEDUCTIONS"
            and meta(row).get(
                "row_role"
            )
            == "DATA"
        )
    ]

    if (
        len(amount_rows)
        != EXPECTED_AMOUNT_COMMERCIAL_ROWS
    ):
        raise RuntimeError(
            "Expected 62 AMOUNT DEDUCTIONS data rows."
        )

    commercial_groups = defaultdict(
        list
    )

    for row in amount_rows:
        title = column_value(
            row,
            "A",
        )

        identity = normalize_identity(
            title
        )

        if identity:
            commercial_groups[
                identity
            ].append(
                row
            )

    if (
        len(commercial_groups)
        != EXPECTED_COMMERCIAL_IDENTITIES
    ):
        raise RuntimeError(
            "Expected 61 unique commercial identities."
        )

    commercial_overlap = (
        set(
            commercial_groups
        )
        & set(
            structured_groups
        )
    )

    if len(commercial_overlap) != 1:
        raise RuntimeError(
            "Expected one structured/commercial overlap."
        )

    commercial_additional = (
        set(
            commercial_groups
        )
        - set(
            structured_groups
        )
    )

    if (
        len(commercial_additional)
        != EXPECTED_COMMERCIAL_ADDITIONAL
    ):
        raise RuntimeError(
            "Expected 60 additional "
            "commercial Services."
        )

    # --------------------------------------------------------
    # Rolling Grants
    # --------------------------------------------------------

    rolling_rows = [
        row
        for row in staged_rows
        if row.sheet_name
        == "Rolling_Grants"
    ]

    if len(rolling_rows) != 7:
        raise RuntimeError(
            "Expected seven Rolling_Grants rows."
        )

    rolling_groups = defaultdict(
        list
    )

    for row in rolling_rows:
        title = column_value(
            row,
            "A",
        )

        identity = normalize_identity(
            title
        )

        if identity:
            rolling_groups[
                identity
            ].append(
                row
            )

    rolling_new = (
        set(
            rolling_groups
        )
        - set(
            structured_groups
        )
        - set(
            commercial_groups
        )
    )

    if len(rolling_new) != EXPECTED_ROLLING_NEW:
        raise RuntimeError(
            "Expected two new Rolling Grant identities."
        )

    # --------------------------------------------------------
    # Existing live title safety
    # --------------------------------------------------------

    live_titles = {
        normalize_identity(
            title
        )
        for title in (
            Service.objects.values_list(
                "title",
                flat=True,
            )
        )
        if normalize_identity(
            title
        )
    }

    final_identities = (
        set(
            structured_groups
        )
        | set(
            commercial_groups
        )
        | rolling_new
    )

    if (
        len(final_identities)
        != EXPECTED_FINAL_SERVICES
    ):
        raise RuntimeError(
            "Expected 162 final Service identities."
        )

    if (
        final_identities
        & live_titles
    ):
        raise RuntimeError(
            "A planned Service now collides "
            "with an existing live Service title."
        )

    # --------------------------------------------------------
    # Slug / Service ID existing safety
    # --------------------------------------------------------

    used_slugs = set(
        Service.objects.values_list(
            "slug",
            flat=True,
        )
    )

    used_service_ids = set(
        Service.objects.values_list(
            "service_id",
            flat=True,
        )
    )

    slug_field = (
        Service._meta.get_field(
            "slug"
        )
    )

    slug_max_length = (
        slug_field.max_length
        or 255
    )

    plans = {}

    structured_kind_counts = Counter()

    commercial_kind_counts = Counter()

    commercial_method_counts = Counter()

    # --------------------------------------------------------
    # Structured Service plans
    # --------------------------------------------------------

    for identity in sorted(
        structured_groups
    ):
        group = structured_groups[
            identity
        ]

        title = ""

        for row in group:
            candidate = payload_value(
                fields(row).get(
                    "scheme_name",
                    {},
                )
            )

            if candidate:
                title = candidate
                break

        if not title:
            raise RuntimeError(
                "A canonical structured identity "
                "has no source title."
            )

        kind = resolve_structured_kind(
            group,
            valid_service_kinds,
        )

        if (
            not kind
            or kind
            not in STRUCTURED_PRIMARY_MAP
        ):
            raise RuntimeError(
                "A structured Service kind "
                "could not be resolved."
            )

        (
            domain_slug,
            category_slug,
        ) = STRUCTURED_PRIMARY_MAP[
            kind
        ]

        pair = (
            domain_slug,
            category_slug,
        )

        if pair not in (
            category_context[
                "available_pairs"
            ]
        ):
            raise RuntimeError(
                "Structured primary category "
                "is unavailable."
            )

        service_id = (
            deterministic_service_id(
                identity
            )
        )

        if service_id in used_service_ids:
            raise RuntimeError(
                "Planned Service ID collides "
                "with existing data."
            )

        used_service_ids.add(
            service_id
        )

        service_slug = (
            deterministic_slug(
                title,
                identity,
                used_slugs,
                slug_max_length,
            )
        )

        plans[
            identity
        ] = {
            "identity": identity,
            "source_family":
                "STRUCTURED",
            "service_id":
                service_id,
            "title":
                title,
            "slug":
                service_slug,
            "domain_slug":
                domain_slug,
            "category_slug":
                category_slug,
            "service_kind":
                kind,
            "status":
                "DRAFT",
            "priority":
                "NORMAL",
            "source_row_ids": [
                row.id
                for row in group
            ],
        }

        structured_kind_counts[
            kind
        ] += 1

    # --------------------------------------------------------
    # Commercial additional Service plans
    # --------------------------------------------------------

    for identity in sorted(
        commercial_additional
    ):
        group = commercial_groups[
            identity
        ]

        title = column_value(
            group[0],
            "A",
        )

        if not title:
            raise RuntimeError(
                "Commercial Service identity "
                "has no source title."
            )

        kind = resolve_commercial_kind(
            identity
        )

        (
            primary_pair,
            method,
            all_matches,
        ) = resolve_commercial_primary(
            identity,
            kind,
        )

        (
            domain_slug,
            category_slug,
        ) = primary_pair

        if primary_pair not in (
            category_context[
                "available_pairs"
            ]
        ):
            raise RuntimeError(
                "Commercial primary category "
                "is unavailable."
            )

        service_id = (
            deterministic_service_id(
                identity
            )
        )

        if service_id in used_service_ids:
            raise RuntimeError(
                "Commercial Service ID collision."
            )

        used_service_ids.add(
            service_id
        )

        service_slug = (
            deterministic_slug(
                title,
                identity,
                used_slugs,
                slug_max_length,
            )
        )

        plans[
            identity
        ] = {
            "identity": identity,
            "source_family":
                "COMMERCIAL",
            "service_id":
                service_id,
            "title":
                title,
            "slug":
                service_slug,
            "domain_slug":
                domain_slug,
            "category_slug":
                category_slug,
            "service_kind":
                kind,
            "status":
                "DRAFT",
            "priority":
                "NORMAL",
            "source_row_ids": [
                row.id
                for row in group
            ],
            "commercial_category_matches":
                all_matches,
            "commercial_resolution_method":
                method,
        }

        commercial_kind_counts[
            kind
        ] += 1

        commercial_method_counts[
            method
        ] += 1

    # --------------------------------------------------------
    # Two new Rolling Grant Service plans
    # --------------------------------------------------------

    for identity in sorted(
        rolling_new
    ):
        group = rolling_groups[
            identity
        ]

        title = column_value(
            group[0],
            "A",
        )

        if not title:
            raise RuntimeError(
                "Rolling Grant has no title."
            )

        pair = (
            DOMAIN_GOVT,
            CAT_GOVT_GRANTS,
        )

        if pair not in (
            category_context[
                "available_pairs"
            ]
        ):
            raise RuntimeError(
                "Government Grants Category unavailable."
            )

        service_id = (
            deterministic_service_id(
                identity
            )
        )

        if service_id in used_service_ids:
            raise RuntimeError(
                "Rolling Grant Service ID collision."
            )

        used_service_ids.add(
            service_id
        )

        service_slug = (
            deterministic_slug(
                title,
                identity,
                used_slugs,
                slug_max_length,
            )
        )

        plans[
            identity
        ] = {
            "identity": identity,
            "source_family":
                "ROLLING_GRANTS",
            "service_id":
                service_id,
            "title":
                title,
            "slug":
                service_slug,
            "domain_slug":
                DOMAIN_GOVT,
            "category_slug":
                CAT_GOVT_GRANTS,
            "service_kind":
                "GRANT",
            "status":
                "DRAFT",
            "priority":
                "NORMAL",
            "source_row_ids": [
                row.id
                for row in group
            ],
        }

    if len(plans) != EXPECTED_FINAL_SERVICES:
        raise RuntimeError(
            "Service planning did not produce 162 records."
        )

    expected_structured_kind_counts = {
        "CERTIFICATION": 5,
        "EQUITY": 14,
        "GOVT_SCHEME": 47,
        "GRANT": 31,
        "LOAN": 2,
        "SUBSIDY": 1,
    }

    if (
        dict(
            structured_kind_counts
        )
        != expected_structured_kind_counts
    ):
        raise RuntimeError(
            "Structured Service kind totals "
            "differ from Contract v3."
        )

    expected_commercial_kind_counts = {
        "CERTIFICATION": 10,
        "OTHER": 40,
        "REGISTRATION": 10,
    }

    if (
        dict(
            commercial_kind_counts
        )
        != expected_commercial_kind_counts
    ):
        raise RuntimeError(
            "Commercial Service kind totals "
            "differ from Contract v3."
        )

    if (
        commercial_method_counts[
            "TITLE_SIGNAL"
        ]
        != 26
    ):
        raise RuntimeError(
            "Expected 26 title-signal "
            "commercial mappings."
        )

    if (
        commercial_method_counts[
            "GENERIC_CATEGORY"
        ]
        != 34
    ):
        raise RuntimeError(
            "Expected 34 generic-category "
            "commercial mappings."
        )

    return {
        "plans": plans,
        "structured_groups":
            structured_groups,
        "commercial_groups":
            commercial_groups,
        "commercial_overlap":
            commercial_overlap,
        "commercial_additional":
            commercial_additional,
        "rolling_groups":
            rolling_groups,
        "rolling_new":
            rolling_new,
        "structured_kind_counts":
            structured_kind_counts,
        "commercial_kind_counts":
            commercial_kind_counts,
        "commercial_method_counts":
            commercial_method_counts,
    }


# ============================================================
# BUILD CLASSIFICATION PLAN
# ============================================================

def build_classifications(
    service_context,
):
    plans = (
        service_context[
            "plans"
        ]
    )

    structured_groups = (
        service_context[
            "structured_groups"
        ]
    )

    commercial_groups = (
        service_context[
            "commercial_groups"
        ]
    )

    classification_by_key = {}

    # --------------------------------------------------------
    # Structured sheet classifications
    # --------------------------------------------------------

    for identity, group in (
        structured_groups.items()
    ):
        service_plan = plans[
            identity
        ]

        primary_pair = (
            service_plan[
                "domain_slug"
            ],
            service_plan[
                "category_slug"
            ],
        )

        for row in group:
            labels = set(
                SOURCE_SHEET_CLASSIFICATIONS.get(
                    row.sheet_name,
                    (),
                )
            )

            source_type = payload_value(
                fields(row).get(
                    "scheme_type",
                    {},
                )
            )

            for signal in (
                source_type_signals(
                    source_type
                )
            ):
                label = (
                    KIND_CLASSIFICATION.get(
                        signal
                    )
                )

                if label:
                    labels.add(
                        label
                    )

            for label in sorted(
                labels
            ):
                pair = (
                    CLASSIFICATION_CATEGORY[
                        label
                    ]
                )

                # Primary category already describes it.
                if pair == primary_pair:
                    continue

                key = (
                    identity,
                    pair[0],
                    pair[1],
                )

                if key not in classification_by_key:
                    classification_by_key[
                        key
                    ] = {
                        "service_identity":
                            identity,
                        "domain_slug":
                            pair[0],
                        "category_slug":
                            pair[1],
                        "source_import_row_id":
                            row.id,
                        "reason":
                            "STRUCTURED_TAXONOMY",
                    }

    # --------------------------------------------------------
    # Commercial title-signal secondary categories
    # --------------------------------------------------------

    for identity, group in (
        commercial_groups.items()
    ):
        # The one overlap maps to the structured Service.
        service_plan = plans[
            identity
        ]

        primary_pair = (
            service_plan[
                "domain_slug"
            ],
            service_plan[
                "category_slug"
            ],
        )

        matches = (
            commercial_category_matches(
                identity
            )
        )

        for pair in matches:
            if pair == primary_pair:
                continue

            key = (
                identity,
                pair[0],
                pair[1],
            )

            if key not in classification_by_key:
                classification_by_key[
                    key
                ] = {
                    "service_identity":
                        identity,
                    "domain_slug":
                        pair[0],
                    "category_slug":
                        pair[1],
                    "source_import_row_id":
                        group[0].id,
                    "reason":
                        "COMMERCIAL_TITLE_SIGNAL",
                }

    return list(
        classification_by_key.values()
    )


# ============================================================
# BUILD COMMERCIAL RECORD PLAN
# ============================================================

def build_commercial_records(
    service_context,
):
    plans = (
        service_context[
            "plans"
        ]
    )

    structured_groups = (
        service_context[
            "structured_groups"
        ]
    )

    commercial_groups = (
        service_context[
            "commercial_groups"
        ]
    )

    commercial_plans = []

    structured_count = 0

    # --------------------------------------------------------
    # 99 structured minimum-charge records
    # --------------------------------------------------------

    for identity, group in (
        structured_groups.items()
    ):
        values = []

        for row in group:
            value = payload_value(
                fields(row).get(
                    "minimum_charge",
                    {},
                )
            )

            if value:
                values.append(
                    (
                        row,
                        value,
                    )
                )

        unique_values = {
            value
            for row, value
            in values
        }

        if len(unique_values) > 1:
            raise RuntimeError(
                "Structured minimum-charge conflict."
            )

        if not values:
            continue

        source_row, value = (
            values[0]
        )

        commercial_plans.append(
            {
                "service_identity":
                    identity,
                "label":
                    "Structured minimum charge",
                "minimum_charge_raw":
                    value,
                "minimum_charge":
                    None,
                "government_fee_raw":
                    "",
                "government_fee":
                    None,
                "vendor_cost_raw":
                    "",
                "vendor_cost":
                    None,
                "bdm_deduction_raw":
                    "",
                "bdm_deduction":
                    None,
                "remarks":
                    "",
                "visibility":
                    "ADMIN_ONLY",
                "source_import_row_id":
                    source_row.id,
                "is_active":
                    True,
                "source_family":
                    "STRUCTURED",
            }
        )

        structured_count += 1

    if (
        structured_count
        != EXPECTED_STRUCTURED_COMMERCIAL
    ):
        raise RuntimeError(
            "Expected 99 structured "
            "ServiceCommercial plans."
        )

    # --------------------------------------------------------
    # 62 AMOUNT DEDUCTIONS records
    # --------------------------------------------------------

    amount_count = 0

    for identity, group in (
        commercial_groups.items()
    ):
        if identity not in plans:
            raise RuntimeError(
                "Commercial source row does not "
                "resolve to a planned Service."
            )

        for row in group:
            commercial_plans.append(
                {
                    "service_identity":
                        identity,
                    "label":
                        column_value(
                            row,
                            "A",
                        ),
                    "minimum_charge_raw":
                        column_value(
                            row,
                            "B",
                        ),
                    "minimum_charge":
                        None,
                    "government_fee_raw":
                        "",
                    "government_fee":
                        None,
                    "vendor_cost_raw":
                        column_value(
                            row,
                            "C",
                        ),
                    "vendor_cost":
                        None,
                    "bdm_deduction_raw":
                        column_value(
                            row,
                            "D",
                        ),
                    "bdm_deduction":
                        None,
                    "remarks":
                        column_value(
                            row,
                            "E",
                        ),
                    "visibility":
                        "ADMIN_ONLY",
                    "source_import_row_id":
                        row.id,
                    "is_active":
                        True,
                    "source_family":
                        "AMOUNT_DEDUCTIONS",
                }
            )

            amount_count += 1

    if (
        amount_count
        != EXPECTED_AMOUNT_COMMERCIAL_ROWS
    ):
        raise RuntimeError(
            "Expected 62 AMOUNT DEDUCTIONS "
            "ServiceCommercial plans."
        )

    if (
        len(commercial_plans)
        != EXPECTED_COMMERCIAL_RECORDS
    ):
        raise RuntimeError(
            "Expected 161 total "
            "ServiceCommercial plans."
        )

    return commercial_plans


# ============================================================
# MODEL-AWARE VALIDATION
# ============================================================

def validate_char_length(
    model,
    field_name,
    value,
    label,
):
    field = model._meta.get_field(
        field_name
    )

    max_length = getattr(
        field,
        "max_length",
        None,
    )

    if (
        max_length
        and value is not None
        and len(str(value)) > max_length
    ):
        raise RuntimeError(
            f"{label} exceeds model max_length."
        )


def validate_core_plan(
    category_context,
    service_context,
    classification_plans,
    commercial_plans,
):
    service_plans = (
        service_context[
            "plans"
        ]
    )

    available_pairs = (
        category_context[
            "available_pairs"
        ]
    )

    service_kind_choices = {
        str(value)
        for value, label
        in Service._meta.get_field(
            "service_kind"
        ).choices
    }

    status_choices = {
        str(value)
        for value, label
        in Service._meta.get_field(
            "status"
        ).choices
    }

    priority_choices = {
        str(value)
        for value, label
        in Service._meta.get_field(
            "priority"
        ).choices
    }

    service_ids = set()

    slugs = set()

    for plan in (
        service_plans.values()
    ):
        if (
            plan[
                "service_kind"
            ]
            not in service_kind_choices
        ):
            raise RuntimeError(
                "Invalid planned service_kind."
            )

        if (
            plan["status"]
            not in status_choices
        ):
            raise RuntimeError(
                "Invalid planned Service status."
            )

        if (
            plan["priority"]
            not in priority_choices
        ):
            raise RuntimeError(
                "Invalid planned Service priority."
            )

        pair = (
            plan["domain_slug"],
            plan["category_slug"],
        )

        if pair not in available_pairs:
            raise RuntimeError(
                "Planned Service references "
                "an unavailable category."
            )

        if (
            plan["service_id"]
            in service_ids
        ):
            raise RuntimeError(
                "Duplicate planned service_id."
            )

        service_ids.add(
            plan["service_id"]
        )

        if plan["slug"] in slugs:
            raise RuntimeError(
                "Duplicate planned Service slug."
            )

        slugs.add(
            plan["slug"]
        )

        validate_char_length(
            Service,
            "service_id",
            plan["service_id"],
            "Service ID",
        )

        validate_char_length(
            Service,
            "title",
            plan["title"],
            "Service title",
        )

        validate_char_length(
            Service,
            "slug",
            plan["slug"],
            "Service slug",
        )

    classification_keys = set()

    for item in classification_plans:
        if (
            item[
                "service_identity"
            ]
            not in service_plans
        ):
            raise RuntimeError(
                "Classification references "
                "unknown Service."
            )

        pair = (
            item["domain_slug"],
            item["category_slug"],
        )

        if pair not in available_pairs:
            raise RuntimeError(
                "Classification references "
                "unavailable Category."
            )

        key = (
            item[
                "service_identity"
            ],
            item[
                "domain_slug"
            ],
            item[
                "category_slug"
            ],
        )

        if key in classification_keys:
            raise RuntimeError(
                "Duplicate ServiceClassification plan."
            )

        classification_keys.add(
            key
        )

    visibility_choices = {
        str(value)
        for value, label
        in ServiceCommercial._meta.get_field(
            "visibility"
        ).choices
    }

    for item in commercial_plans:
        if (
            item[
                "service_identity"
            ]
            not in service_plans
        ):
            raise RuntimeError(
                "Commercial record references "
                "unknown Service."
            )

        if (
            item["visibility"]
            not in visibility_choices
        ):
            raise RuntimeError(
                "Invalid commercial visibility."
            )

        validate_char_length(
            ServiceCommercial,
            "label",
            item["label"],
            "ServiceCommercial label",
        )

        if (
            item["minimum_charge"]
            is not None
            or item["government_fee"]
            is not None
            or item["vendor_cost"]
            is not None
            or item["bdm_deduction"]
            is not None
        ):
            raise RuntimeError(
                "Numeric commercial field was "
                "populated during raw-only planning."
            )

    if len(service_plans) != 162:
        raise RuntimeError(
            "Core Service count != 162."
        )

    if len(
        category_context[
            "create"
        ]
    ) != 8:
        raise RuntimeError(
            "Category creation plan != 8."
        )

    if len(commercial_plans) != 161:
        raise RuntimeError(
            "ServiceCommercial plan != 161."
        )

    return {
        "services":
            len(service_plans),
        "categories_to_create":
            len(
                category_context[
                    "create"
                ]
            ),
        "classifications":
            len(
                classification_plans
            ),
        "commercial_records":
            len(
                commercial_plans
            ),
    }


# ============================================================
# PUBLIC PLANNER
# ============================================================

def build_core_transformation_plan():
    (
        contract,
        batch,
        staged_rows,
    ) = load_verified_context()

    vocabulary = (
        model_vocabulary()
    )

    category_context = (
        build_category_plan()
    )

    service_context = (
        build_services(
            staged_rows,
            category_context,
            vocabulary,
        )
    )

    classification_plans = (
        build_classifications(
            service_context
        )
    )

    commercial_plans = (
        build_commercial_records(
            service_context
        )
    )

    validation = (
        validate_core_plan(
            category_context,
            service_context,
            classification_plans,
            commercial_plans,
        )
    )

    return {
        "contract_version":
            contract[
                "contract"
            ][
                "version"
            ],
        "batch_id":
            batch.id,
        "staged_row_count":
            len(staged_rows),
        "categories":
            category_context[
                "create"
            ],
        "services":
            service_context[
                "plans"
            ],
        "classifications":
            classification_plans,
        "commercial":
            commercial_plans,
        "validation":
            validation,
        "structured_kind_counts":
            dict(
                service_context[
                    "structured_kind_counts"
                ]
            ),
        "commercial_kind_counts":
            dict(
                service_context[
                    "commercial_kind_counts"
                ]
            ),
        "commercial_method_counts":
            dict(
                service_context[
                    "commercial_method_counts"
                ]
            ),
    }
