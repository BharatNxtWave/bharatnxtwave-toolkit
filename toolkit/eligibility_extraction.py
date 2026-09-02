"""
STRUCTURED_ELIGIBILITY_V1

Conservative deterministic extraction of structured
eligibility facts from existing BDE-visible Toolkit text.
"""

import re
from decimal import Decimal

from .models import ServiceContentSection


def clean_text(value):

    value = str(value or "")

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = value.casefold()

    value = (
        value
        .replace("–", "-")
        .replace("—", "-")
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def has_regex(text, pattern):

    return bool(
        re.search(
            pattern,
            text,
            flags=re.I,
        )
    )


def add_unique(target, value):

    if value not in target:
        target.append(value)


def eligibility_source(service):

    values = [
        service.eligibility_summary,
        service.applicable_for_raw,
        service.restrictions,
        service.important_notes,
    ]

    sections = (
        ServiceContentSection.objects
        .filter(
            service=service,
            visibility="BDE",
            section_type="ELIGIBILITY",
        )
        .values_list(
            "content",
            flat=True,
        )
    )

    values.extend(sections)

    return clean_text(
        " ".join(
            str(value or "")
            for value in values
        )
    )


def extract_business_types(text):

    found = []

    rules = (
        (
            "Private Limited",
            (
                r"\bpvt\.?\s*ltd\.?\b",
                r"\bprivate\s+limited\b",
            ),
        ),
        (
            "LLP",
            (
                r"\bllp\b",
                r"\blimited\s+liability\s+partnership\b",
            ),
        ),
        (
            "OPC",
            (
                r"\bopc\b",
                r"\bone\s+person\s+company\b",
            ),
        ),
        (
            "Proprietorship",
            (
                r"\bproprietorship\b",
                r"\bsole\s+proprietorship\b",
                r"\bproprietary\b",
            ),
        ),
        (
            "Public Limited",
            (
                r"\bpublic\s+limited\b",
            ),
        ),
        (
            "Section 8 Company",
            (
                r"\bsection\s*8\b",
            ),
        ),
        (
            "Society",
            (
                r"\bregistered\s+society\b",
                r"\bsociety\b",
            ),
        ),
        (
            "Trust",
            (
                r"\btrust\b",
            ),
        ),
        (
            "HUF",
            (
                r"\bhuf\b",
            ),
        ),
        (
            "Individual",
            (
                r"\bindividuals?\b",
            ),
        ),
        (
            "Cooperative",
            (
                r"\bco-?operative\b",
                r"\bcooperative\b",
            ),
        ),
    )

    for label, patterns in rules:

        if any(
            has_regex(text, pattern)
            for pattern in patterns
        ):
            add_unique(found, label)


    partnership_text = re.sub(
        r"limited\s+liability\s+partnership",
        " ",
        text,
    )

    if any(
        has_regex(
            partnership_text,
            pattern,
        )
        for pattern in (
            r"\bregistered\s+partnership\b",
            r"\breg\.?\s+partnership\b",
            r"\bpartnership\s+firm\b",
            r"\bpartnership\b",
        )
    ):
        add_unique(
            found,
            "Partnership",
        )

    return found


def extract_business_stages(text):

    found = []

    rules = (
        (
            "Idea Stage",
            (
                r"\bidea\s+stage\b",
                r"\bidea-stage\b",
            ),
        ),
        (
            "PoC Stage",
            (
                r"\bpoc\s+stage\b",
                r"\bproof\s+of\s+concept\b",
            ),
        ),
        (
            "Prototype Stage",
            (
                r"\bprototype\s+stage\b",
            ),
        ),
        (
            "MVP Stage",
            (
                r"\bmvp\b",
                r"\bminimum\s+viable\s+product\b",
            ),
        ),
        (
            "Early Stage",
            (
                r"\bearly\s+stage\b",
            ),
        ),
        (
            "Growth Stage",
            (
                r"\bgrowth\s+stage\b",
            ),
        ),
        (
            "Scale-up Stage",
            (
                r"\bscale[- ]?up\s+stage\b",
                r"\bscaleup\s+stage\b",
            ),
        ),
        (
            "Pre-Revenue",
            (
                r"\bpre[- ]?revenue\b",
            ),
        ),
        (
            "Revenue Generating",
            (
                r"\brevenue[- ]?generating\b",
            ),
        ),
    )

    for label, patterns in rules:

        if any(
            has_regex(text, pattern)
            for pattern in patterns
        ):
            add_unique(found, label)

    return found


STATE_RULES = (
    ("Andhra Pradesh", r"\bandhra\s+pradesh\b"),
    ("Arunachal Pradesh", r"\barunachal\s+pradesh\b"),
    ("Assam", r"\bassam\b"),
    ("Bihar", r"\bbihar\b"),
    ("Chhattisgarh", r"\bchhattisgarh\b"),
    ("Goa", r"\bgoa\b"),
    ("Gujarat", r"\bgujarat\b"),
    ("Haryana", r"\bharyana\b"),
    ("Himachal Pradesh", r"\bhimachal\s+pradesh\b"),
    ("Jharkhand", r"\bjharkhand\b"),
    ("Karnataka", r"\bkarnataka\b"),
    ("Kerala", r"\bkerala\b"),
    ("Madhya Pradesh", r"\bmadhya\s+pradesh\b"),
    ("Maharashtra", r"\bmaharashtra\b"),
    ("Manipur", r"\bmanipur\b"),
    ("Meghalaya", r"\bmeghalaya\b"),
    ("Mizoram", r"\bmizoram\b"),
    ("Nagaland", r"\bnagaland\b"),
    ("Odisha", r"\bodisha\b"),
    ("Punjab", r"\bpunjab\b"),
    ("Rajasthan", r"\brajasthan\b"),
    ("Sikkim", r"\bsikkim\b"),
    ("Tamil Nadu", r"\btamil\s*nadu\b"),
    ("Telangana", r"\btelangana\b"),
    ("Tripura", r"\btripura\b"),
    ("Uttar Pradesh", r"\buttar\s+pradesh\b"),
    ("Uttarakhand", r"\buttarakhand\b"),
    ("West Bengal", r"\bwest\s+bengal\b"),
)


def extract_states(text):

    if has_regex(
        text,
        r"\bpan\s+india\b",
    ):
        return ["Pan India"]

    found = []

    for label, pattern in STATE_RULES:

        if has_regex(text, pattern):
            add_unique(found, label)

    return found


def extract_industries(text):

    found = []

    rules = (
        (
            "Manufacturing",
            (
                r"\bmanufacturing\b",
                r"\bmanufacturing\s+enterprises?\b",
            ),
        ),
        (
            "Technology",
            (
                r"\btech[- ]enabled\b",
                r"\btechnology\s+and\s+innovation\b",
                r"\btechnology\b",
            ),
        ),
        (
            "Agriculture",
            (
                r"\bagriculture\b",
                r"\bagri[- ]?tech\b",
                r"\bagro[- ]based\b",
            ),
        ),
        (
            "Food Processing",
            (
                r"\bfood\s+processing\b",
            ),
        ),
        (
            "Animal Husbandry",
            (
                r"\banimal\s+husbandry\b",
                r"\blivestock\b",
            ),
        ),
        (
            "IT / ITeS",
            (
                r"\bit\/ites\b",
                r"\bites\b",
                r"\binformation\s+technology\b",
            ),
        ),
        (
            "R&D",
            (
                r"\br&d\b",
                r"\bresearch\s+and\s+development\b",
            ),
        ),
    )

    for label, patterns in rules:

        if any(
            has_regex(text, pattern)
            for pattern in patterns
        ):
            add_unique(found, label)

    return found


def extract_founder_categories(
    service,
    text,
):

    found = []

    title = clean_text(
        service.title
    )

    if (
        has_regex(
            title,
            r"\bwomen\b",
        )
        and has_regex(
            text,
            r"\bwomen\b",
        )
    ):
        add_unique(
            found,
            "Women",
        )


    explicit_rules = (
        (
            "Women",
            (
                r"\bonly\s+(?:for\s+)?women\b",
                r"\bwomen\s+entrepreneurs?\s+only\b",
                r"\bexclusively\s+for\s+women\b",
            ),
        ),
        (
            "SC",
            (
                r"\bonly\s+(?:for\s+)?sc\b",
                r"\bexclusively\s+for\s+sc\b",
                r"\bscheduled\s+caste\s+only\b",
            ),
        ),
        (
            "ST",
            (
                r"\bonly\s+(?:for\s+)?st\b",
                r"\bexclusively\s+for\s+st\b",
                r"\bscheduled\s+tribe\s+only\b",
            ),
        ),
        (
            "OBC",
            (
                r"\bonly\s+(?:for\s+)?obc\b",
                r"\bexclusively\s+for\s+obc\b",
            ),
        ),
    )

    for label, patterns in explicit_rules:

        if any(
            has_regex(text, pattern)
            for pattern in patterns
        ):
            add_unique(
                found,
                label,
            )

    return found


def extract_business_age(text):

    max_months = None

    patterns = (
        r"incorporated\s+(?:within|in)\s+the\s+last\s+(\d+)\s+years?",
        r"incorporated\s+(?:within|in)\s+last\s+(\d+)\s+years?",
        r"been\s+incorporated\s+in\s+the\s+last\s+(\d+)\s+years?",
        r"period\s+of\s+existence.*?not\s+.*?exceed(?:ing)?\s+(\d+)\s+years?",
        r"up\s+to\s+(\d+)\s+years?\s+from\s+the\s+date\s+of\s+(?:its\s+)?(?:incorporation|registration)",
        r"within\s+the\s+last\s+(\d+)\s+years?",
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:

            max_months = (
                int(match.group(1))
                * 12
            )

            break

    return {
        "min_business_age_months":
            None,
        "max_business_age_months":
            max_months,
    }


def money_to_lakh(
    value,
    unit,
):

    value = Decimal(value)
    unit = unit.casefold()

    if unit in {
        "crore",
        "crores",
        "cr",
    }:
        value *= Decimal("100")

    return value


def extract_turnover(text):

    max_turnover = None

    patterns = (
        r"(?:annual\s+)?turnover"
        r".{0,80}?"
        r"(?:not\s+exceeding|not\s+exceeded|"
        r"has\s+not\s+exceeded|up\s+to|below)"
        r".{0,30}?"
        r"(?:rs\.?|inr|₹)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(lakh|lakhs|lac|lacs|crore|crores|cr)\b",

        r"(?:not\s+exceeding|not\s+exceeded)"
        r".{0,30}?"
        r"(?:rs\.?|inr|₹)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(lakh|lakhs|lac|lacs|crore|crores|cr)"
        r".{0,30}?"
        r"turnover",
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:

            max_turnover = money_to_lakh(
                match.group(1),
                match.group(2),
            )

            break

    return {
        "min_turnover":
            None,
        "max_turnover":
            max_turnover,
    }


def extract_service(service):

    source = eligibility_source(
        service
    )

    age = extract_business_age(
        source
    )

    turnover = extract_turnover(
        source
    )

    return (
        {
            "business_types":
                extract_business_types(
                    source
                ),

            "business_stages":
                extract_business_stages(
                    source
                ),

            "industries":
                extract_industries(
                    source
                ),

            "applicable_states":
                extract_states(
                    source
                ),

            "founder_categories":
                extract_founder_categories(
                    service,
                    source,
                ),

            "min_business_age_months":
                age[
                    "min_business_age_months"
                ],

            "max_business_age_months":
                age[
                    "max_business_age_months"
                ],

            "min_turnover":
                turnover[
                    "min_turnover"
                ],

            "max_turnover":
                turnover[
                    "max_turnover"
                ],
        },
        source,
    )
