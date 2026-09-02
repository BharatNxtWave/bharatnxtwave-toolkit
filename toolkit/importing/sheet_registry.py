import re


SCHEME_TABLES = (
    "GRANT",
    "Women_GRANT",
    "Agriculture_FUND",
    "NGO_GRANT",
    "EQUITY",
    "GRANTDEBTEQUITY",
    "DEBTEQUITY",
    "LOAN ONLY",
    "LOANSUBSIDY",
    "CERTGEM",
)


REFERENCE_TABLES = (
    "BENEFITS",
    "AMOUNT DEDUCTIONS",
)


COMPARISON_TABLES = (
    "LOAN",
)


KNOWLEDGE_SHEETS = (
    "START_UP INDIA",
    "TAX_CERT",
    "SEED FUND",
    "PVT",
    "LLP",
)


COMMUNICATION_SHEETS = (
    "ONBOARDING_MAIL",
)


ROLLING_GRANT_SHEETS = (
    "Rolling_Grants",
)


EXPECTED_SHEETS = (
    *SCHEME_TABLES,
    "BENEFITS",
    "START_UP INDIA",
    "LOAN",
    "TAX_CERT",
    "SEED FUND",
    "PVT",
    "LLP",
    "AMOUNT DEDUCTIONS",
    "ONBOARDING_MAIL",
    "Rolling_Grants",
)


def sheet_family(sheet_name):

    if sheet_name in SCHEME_TABLES:
        return "SCHEME_TABLE"

    if sheet_name in REFERENCE_TABLES:
        return "REFERENCE_TABLE"

    if sheet_name in COMPARISON_TABLES:
        return "COMPARISON_MATRIX"

    if sheet_name in KNOWLEDGE_SHEETS:
        return "KNOWLEDGE"

    if sheet_name in COMMUNICATION_SHEETS:
        return "COMMUNICATION"

    if sheet_name in ROLLING_GRANT_SHEETS:
        return "ROLLING_GRANTS"

    return "UNKNOWN"


def normalize_header(value):

    if value is None:
        return ""

    text = str(value).strip().casefold()

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


HEADER_ALIASES = {

    "serial_number": {
        "sr no",
        "sr no.",
        "sr. no.",
        "sr. no",
        "sr no",
        "sl no",
        "serial no",
        "serial number",
    },

    "scheme_name": {
        "scheme name",
    },

    "benefits": {
        "benefits",
        "benefit",
    },

    "focus_sectors": {
        "focus sectors",
        "focus sector",
        "sectors",
        "sector",
    },

    "eligibility": {
        "eligibility criteria",
        "eligibility",
    },

    "deadline": {
        "last date",
        "deadline",
        "application deadline",
    },

    "funding_organisation": {
        "funding organisation",
        "funding organization",
        "organisation",
        "organization",
    },

    "scheme_type": {
        "type of scheme",
        "scheme type",
        "type",
    },

    "applicable_for": {
        "applicable for",
        "application for",
    },

    "portal_link": {
        "portal links",
        "portal link",
        "portal",
    },

    "minimum_charge": {
        "min charge upfront",
        "minimum charge upfront",
        "min charge",
        "minimum charges",
    },

    "additional_info": {
        "additional info",
        "additional information",
    },

    "government_charge": {
        "govt charges if any",
        "govt charge if any",
        "govt charges",
        "govt registration charge",
        "government charge",
        "government charges",
    },

    "flyer": {
        "flyer",
    },
}


ALIAS_LOOKUP = {}

for canonical, aliases in HEADER_ALIASES.items():

    for alias in aliases:

        ALIAS_LOOKUP[
            normalize_header(alias)
        ] = canonical


def canonical_header(value):

    return ALIAS_LOOKUP.get(
        normalize_header(value)
    )
