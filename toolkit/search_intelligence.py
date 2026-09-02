import re


SEARCH_STOPWORDS = {
    # English conversational filler
    "a",
    "an",
    "and",
    "are",
    "available",
    "best",
    "business",
    "businesses",
    "client",
    "company",
    "companies",
    "entrepreneur",
    "entrepreneurs",
    "find",
    "for",
    "founder",
    "founders",
    "get",
    "give",
    "help",
    "is",
    "looking",
    "need",
    "needs",
    "of",
    "or",
    "related",
    "relating",
    "scheme",
    "schemes",
    "service",
    "services",
    "support",
    "the",
    "to",
    "want",
    "wants",
    "with",

    # Hinglish conversational filler
    "aur",
    "chahiye",
    "chahie",
    "chaiye",
    "hai",
    "hain",
    "hamare",
    "hume",
    "humko",
    "karna",
    "karni",
    "ke",
    "ki",
    "ko",
    "koi",
    "kuch",
    "liye",
    "main",
    "mein",
    "mere",
    "meri",
    "milega",
    "mil",
    "mujhe",
    "sakta",
    "sakti",
    "tak",
    "wala",
    "wale",
    "wali",

    # Consumed separately by amount parser
    "lakh",
    "lakhs",
    "lac",
    "lacs",
    "crore",
    "crores",
    "cr",
    "rs",
    "rupee",
    "rupees",
}


CONCEPT_VARIANTS = {

    "agriculture": (
        "agriculture",
        "agri",
        "agritech",
        "agri-tech",
        "farming",
        "krishi",
        "kheti",
    ),

    "women": (
        "women",
        "woman",
        "female",
        "mahila",
    ),

    "grant": (
        "grant",
        "grants",
    ),

    "loan": (
        "loan",
        "loans",
        "debt",
        "credit",
    ),

    "subsidy": (
        "subsidy",
        "subsidies",
    ),

    "equity": (
        "equity",
        "venture capital",
        "vc",
        "investment",
    ),

    "funding": (
        "funding",
        "fund",
        "financial assistance",
        "grant",
        "loan",
        "equity",
        "subsidy",
    ),

    "ngo": (
        "ngo",
        "nonprofit",
        "non-profit",
        "non profit",
        "not for profit",
        "section 8",
    ),

    "startup": (
        "startup",
        "start-up",
        "start up",
    ),

    "food": (
        "food",
        "foodtech",
        "food tech",
        "food technology",
        "food and beverage",
        "fnb",
    ),

    "manufacturing": (
        "manufacturing",
        "manufacturer",
        "manufacture",
    ),

    "animal_husbandry": (
        "animal husbandry",
        "livestock",
        "dairy",
        "poultry",
    ),

    "seed": (
        "seed",
        "seed fund",
        "seed funding",
    ),

    "registration": (
        "registration",
        "register",
        "incorporation",
        "incorporate",
    ),

    "compliance": (
        "compliance",
        "compliances",
    ),

    "certification": (
        "certificate",
        "certification",
        "certifications",
    ),

    "tax": (
        "tax",
        "income tax",
        "taxation",
    ),

    "gst": (
        "gst",
        "goods and services tax",
    ),

    "msme": (
        "msme",
        "udyam",
        "micro small medium",
    ),

    "export": (
        "export",
        "exports",
        "exporter",
    ),

    "technology": (
        "technology",
        "tech",
    ),
}


TOKEN_TO_CONCEPT = {

    "agriculture": "agriculture",
    "agri": "agriculture",
    "agritech": "agriculture",
    "farming": "agriculture",
    "farmer": "agriculture",
    "farmers": "agriculture",
    "krishi": "agriculture",
    "kheti": "agriculture",

    "women": "women",
    "woman": "women",
    "female": "women",
    "mahila": "women",

    "grant": "grant",
    "grants": "grant",

    "loan": "loan",
    "loans": "loan",
    "debt": "loan",
    "credit": "loan",

    "subsidy": "subsidy",
    "subsidies": "subsidy",

    "equity": "equity",
    "investment": "equity",
    "investor": "equity",
    "vc": "equity",

    "fund": "funding",
    "funds": "funding",
    "funding": "funding",
    "finance": "funding",
    "financing": "funding",

    "ngo": "ngo",
    "nonprofit": "ngo",

    "startup": "startup",
    "startups": "startup",

    "food": "food",
    "foodtech": "food",
    "fnb": "food",

    "manufacturing": "manufacturing",
    "manufacturer": "manufacturing",
    "manufacture": "manufacturing",

    "husbandry": "animal_husbandry",
    "livestock": "animal_husbandry",
    "dairy": "animal_husbandry",
    "poultry": "animal_husbandry",

    "seed": "seed",

    "registration": "registration",
    "register": "registration",
    "incorporation": "registration",
    "incorporate": "registration",

    "compliance": "compliance",
    "compliances": "compliance",

    "certificate": "certification",
    "certification": "certification",

    "tax": "tax",
    "taxation": "tax",

    "gst": "gst",

    "msme": "msme",
    "udyam": "msme",

    "export": "export",
    "exports": "export",
    "exporter": "export",

    "technology": "technology",
    "tech": "technology",
}


PHRASE_TO_CONCEPT = {

    "animal husbandry":
        "animal_husbandry",

    "venture capital":
        "equity",

    "seed funding":
        "seed",

    "seed fund":
        "seed",

    "section 8":
        "ngo",

    "not for profit":
        "ngo",

    "non profit":
        "ngo",

    "start up":
        "startup",

    "agri tech":
        "agriculture",

    "food tech":
        "food",

    "food technology":
        "food",

    "income tax":
        "tax",

    "goods and services tax":
        "gst",
}


SPECIFIC_FINANCE_CONCEPTS = {
    "grant",
    "loan",
    "subsidy",
    "equity",
    "seed",
}


def normalize_query(value):

    value = str(
        value or ""
    ).casefold().strip()

    value = value.replace(
        "&",
        " and "
    )

    value = re.sub(
        r"[-_/]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _phrase_present(text, phrase):

    return bool(
        re.search(
            r"(?<![a-z0-9])"
            + re.escape(phrase)
            + r"(?![a-z0-9])",
            text,
        )
    )


def _amount_variants(number, unit):
    """
    Convert natural amount text into the common source formats
    present in BharatNXT data.

    Example:
        5 lakh

    searches forms including:
        5 lakh
        5.00 lakh
        Rs. 5.00 Lakh
        ₹5.00 lakh
        5 lac
    """

    number = str(
        number
    ).strip()

    canonical_unit = {
        "lac": "lakh",
        "lacs": "lakh",
        "lakhs": "lakh",
        "cr": "crore",
        "crores": "crore",
    }.get(
        unit,
        unit,
    )


    numeric_forms = [
        number
    ]


    try:

        numeric = float(
            number
        )


        if numeric.is_integer():

            fixed = f"{numeric:.2f}"

        else:

            fixed = (
                f"{numeric:.2f}"
                .rstrip("0")
                .rstrip(".")
            )


        if fixed not in numeric_forms:

            numeric_forms.append(
                fixed
            )


        # The source workbook often stores whole lakh values
        # with two decimal places: 5.00, 25.00 etc.
        fixed_two = f"{numeric:.2f}"


        if fixed_two not in numeric_forms:

            numeric_forms.append(
                fixed_two
            )


    except ValueError:

        pass


    if canonical_unit == "lakh":

        units = (
            "lakh",
            "lakhs",
            "lac",
            "lacs",
        )

    else:

        units = (
            "crore",
            "crores",
            "cr",
        )


    prefixes = (
        "",
        "rs ",
        "rs. ",
        "₹",
        "₹ ",
    )


    variants = []


    for numeric_form in numeric_forms:

        for unit_form in units:

            amount = (
                f"{numeric_form} "
                f"{unit_form}"
            )


            for prefix in prefixes:

                variants.append(
                    f"{prefix}{amount}"
                )


    return tuple(
        dict.fromkeys(
            variants
        )
    )


def query_groups(value):

    text = normalize_query(
        value
    )


    if not text:

        return []


    groups = []
    group_keys = []
    seen = set()
    consumed_phrase_tokens = set()


    def add_group(key, variants):

        if key in seen:

            return


        seen.add(
            key
        )

        group_keys.append(
            key
        )

        groups.append(
            tuple(
                dict.fromkeys(
                    str(item).strip()
                    for item in variants
                    if str(item).strip()
                )
            )
        )


    # --------------------------------------------------------
    # PHRASE CONCEPTS
    # --------------------------------------------------------

    for phrase, concept in sorted(
        PHRASE_TO_CONCEPT.items(),
        key=lambda item: len(
            item[0]
        ),
        reverse=True,
    ):

        if not _phrase_present(
            text,
            phrase,
        ):

            continue


        add_group(
            concept,
            CONCEPT_VARIANTS[
                concept
            ],
        )


        consumed_phrase_tokens.update(
            re.findall(
                r"[a-z0-9]+",
                phrase,
            )
        )


    # --------------------------------------------------------
    # MONEY AMOUNTS
    # --------------------------------------------------------

    for match in re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*"
        r"(lakh|lakhs|lac|lacs|crore|crores|cr)\b",
        text,
    ):

        number = match.group(
            1
        )

        unit = match.group(
            2
        )


        canonical_unit = {
            "lac": "lakh",
            "lacs": "lakh",
            "lakhs": "lakh",
            "cr": "crore",
            "crores": "crore",
        }.get(
            unit,
            unit,
        )


        add_group(
            (
                f"amount:{number}:"
                f"{canonical_unit}"
            ),
            _amount_variants(
                number,
                unit,
            ),
        )


    # --------------------------------------------------------
    # TOKENS
    # --------------------------------------------------------

    tokens = re.findall(
        r"[a-z0-9]+",
        text,
    )


    for token in tokens:

        if token in consumed_phrase_tokens:

            continue


        if token.isdigit():

            continue


        if len(token) < 3:

            continue


        if token in SEARCH_STOPWORDS:

            continue


        concept = TOKEN_TO_CONCEPT.get(
            token
        )


        if concept:

            add_group(
                concept,
                CONCEPT_VARIANTS[
                    concept
                ],
            )

        else:

            # Preserve unknown business-specific terms such
            # as FCRA instead of silently deleting them.
            add_group(
                f"literal:{token}",
                (token,),
            )


    # Specific financial intent beats generic funding.
    if (
        "funding" in group_keys
        and any(
            key in SPECIFIC_FINANCE_CONCEPTS
            for key in group_keys
        )
    ):

        groups = [
            variants
            for key, variants
            in zip(
                group_keys,
                groups,
            )
            if key != "funding"
        ]


    return groups
