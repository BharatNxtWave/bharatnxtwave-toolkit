import json
import re
import shutil

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from toolkit.intelligence.workbook_intelligence import (
    AUDIT_DIR,
    detect_section_type,
    json_safe,
)


# ============================================================
# HELPERS
# ============================================================

def txt(value):
    if value is None:
        return ""
    return str(value).strip()


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        txt(value).lower(),
    ).strip()


def field_names(model):
    return {
        field.name
        for field in model._meta.get_fields()
    }


def first_attr(obj, names):
    available = field_names(
        obj.__class__
    )

    for name in names:
        if name not in available:
            continue

        value = getattr(
            obj,
            name,
            None,
        )

        if value is not None:
            return value

    return None


def get_metadata(obj):
    available = field_names(
        obj.__class__
    )

    if "metadata" not in available:
        return {}

    value = getattr(
        obj,
        "metadata",
        {},
    )

    return (
        value
        if isinstance(value, dict)
        else {}
    )


def trim(model, field_name, value):
    value = txt(value)

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
        and len(value) > max_length
    ):
        value = value[:max_length]

    return value


# ============================================================
# SERVICE RESOLUTION
# ============================================================

def resolve_service(section):

    section_fields = field_names(
        section.__class__
    )

    # --------------------------------------------
    # Direct service FK
    # --------------------------------------------

    if "service" in section_fields:

        service = getattr(
            section,
            "service",
            None,
        )

        if service is not None:
            return service, "DIRECT_SERVICE"

    # --------------------------------------------
    # Source ImportRow
    # --------------------------------------------

    for field_name in (
        "source_import_row",
        "import_row",
    ):

        if field_name not in section_fields:
            continue

        row = getattr(
            section,
            field_name,
            None,
        )

        if row is None:
            continue

        service = (
            getattr(
                row,
                "imported_service",
                None,
            )
            or getattr(
                row,
                "matched_service",
                None,
            )
        )

        if service is not None:
            return (
                service,
                "SOURCE_IMPORT_ROW",
            )

    # --------------------------------------------
    # Parent KnowledgeDocument
    # --------------------------------------------

    for field_name in (
        "document",
        "knowledge_document",
    ):

        if field_name not in section_fields:
            continue

        document = getattr(
            section,
            field_name,
            None,
        )

        if document is None:
            continue

        document_fields = field_names(
            document.__class__
        )

        if "service" in document_fields:

            service = getattr(
                document,
                "service",
                None,
            )

            if service is not None:
                return (
                    service,
                    "DOCUMENT_SERVICE",
                )

        for row_field in (
            "source_import_row",
            "import_row",
        ):

            if row_field not in document_fields:
                continue

            row = getattr(
                document,
                row_field,
                None,
            )

            if row is None:
                continue

            service = (
                getattr(
                    row,
                    "imported_service",
                    None,
                )
                or getattr(
                    row,
                    "matched_service",
                    None,
                )
            )

            if service is not None:
                return (
                    service,
                    "DOCUMENT_IMPORT_ROW",
                )

    return None, "UNRESOLVED"


# ============================================================
# SOURCE ROW
# ============================================================

def source_row(section):

    fields = field_names(
        section.__class__
    )

    for name in (
        "source_import_row",
        "import_row",
    ):
        if name in fields:

            row = getattr(
                section,
                name,
                None,
            )

            if row is not None:
                return row

    return None


# ============================================================
# VISIBILITY
# ============================================================

def is_bde_visible(section):

    fields = field_names(
        section.__class__
    )

    if "visibility" in fields:

        return (
            txt(
                getattr(
                    section,
                    "visibility",
                    "",
                )
            ).upper()
            == "BDE"
        )

    # Try parent document.
    for name in (
        "document",
        "knowledge_document",
    ):

        if name not in fields:
            continue

        document = getattr(
            section,
            name,
            None,
        )

        if document is None:
            continue

        document_fields = field_names(
            document.__class__
        )

        if (
            "visibility"
            in document_fields
        ):

            return (
                txt(
                    getattr(
                        document,
                        "visibility",
                        "",
                    )
                ).upper()
                == "BDE"
            )

    # No explicit BDE permission = don't expose.
    return False


# ============================================================
# CONTENT / TITLE / TYPE / ORDER
# ============================================================

def section_content(section):

    value = first_attr(
        section,
        (
            "content",
            "text",
            "body",
            "value",
            "value_raw",
        ),
    )

    return txt(value)


def section_title(section):

    value = first_attr(
        section,
        (
            "title",
            "heading",
            "name",
            "label",
        ),
    )

    return txt(value)


def section_type(section):

    value = first_attr(
        section,
        (
            "section_type",
            "content_type",
            "type",
        ),
    )

    value = txt(value).upper()

    if value:
        return value

    guessed = detect_section_type(
        (
            section_title(section)
            + " "
            + section_content(section)
        )
    )

    return guessed or "OTHER"


def section_order(section):

    value = first_attr(
        section,
        (
            "display_order",
            "sequence",
            "order",
            "position",
        ),
    )

    try:
        return int(value or 0)
    except Exception:
        return 0


def is_heading(section):

    metadata = get_metadata(
        section
    )

    if metadata.get(
        "is_heading"
    ) is True:
        return True

    title = section_title(
        section
    )

    content = section_content(
        section
    )

    return bool(
        title
        and content
        and norm(title) == norm(content)
    )


# ============================================================
# SOURCE TEXT SPLITTER
# ============================================================

LIST_PREFIX = re.compile(
    r"""
    ^\s*
    (?:
        [•●▪◦\-–—*]
        |
        \d+[\.\)]
        |
        [a-zA-Z][\.\)]
    )
    \s+
    """,
    re.X,
)


def split_explicit_list(value):

    value = txt(value)

    if not value:
        return []

    lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]

    items = []

    for line in lines:

        if LIST_PREFIX.search(
            line
        ):

            cleaned = LIST_PREFIX.sub(
                "",
                line,
            ).strip()

            if cleaned:
                items.append(
                    cleaned
                )

    if len(items) >= 2:
        return items

    # Semicolon is much safer than comma
    # for source list extraction.
    if ";" in value:

        parts = [
            part.strip()
            for part in value.split(";")
            if part.strip()
        ]

        if len(parts) >= 2:
            return parts

    return []


# ============================================================
# ELIGIBILITY RULE CLASSIFICATION
# Deterministic only — no LLM guessing.
# ============================================================

def eligibility_rule_type(value):

    text = norm(value)

    disqualifiers = (
        "not eligible",
        "ineligible",
        "cannot apply",
        "shall not",
        "not allowed",
    )

    if any(
        phrase in text
        for phrase in disqualifiers
    ):
        return "DISQUALIFIER"

    required = (
        "must ",
        "required",
        "shall ",
        "has to ",
        "need to ",
        "needs to ",
        "at least ",
        "not more than ",
        "minimum ",
        "maximum ",
        "only eligible",
    )

    if any(
        phrase in text
        for phrase in required
    ):
        return "REQUIRED"

    if "optional" in text:
        return "OPTIONAL"

    return "INFORMATION"


# ============================================================
# DOCUMENT MANDATORY CONFIDENCE
# ============================================================

def documents_are_required(
    heading,
    content,
):

    value = norm(
        f"{heading} {content}"
    )

    required_markers = (
        "required document",
        "documents required",
        "mandatory document",
        "documents mandatory",
        "must submit",
        "shall submit",
        "required to submit",
        "documents needed",
    )

    return any(
        marker in value
        for marker
        in required_markers
    )


# ============================================================
# COMMAND
# ============================================================

class Command(BaseCommand):

    help = (
        "Apply BDE-visible linked "
        "KnowledgeSection intelligence."
    )

    def handle(
        self,
        *args,
        **options,
    ):

        print("=" * 78)
        print(
            "BHARATNXT INTELLIGENCE "
            "— KNOWLEDGE APPLY"
        )
        print("=" * 78)

        Service = apps.get_model(
            "toolkit",
            "Service",
        )

        KnowledgeDocument = (
            apps.get_model(
                "toolkit",
                "KnowledgeDocument",
            )
        )

        KnowledgeSection = (
            apps.get_model(
                "toolkit",
                "KnowledgeSection",
            )
        )

        ServiceContentSection = (
            apps.get_model(
                "toolkit",
                "ServiceContentSection",
            )
        )

        EligibilityRule = (
            apps.get_model(
                "toolkit",
                "EligibilityRule",
            )
        )

        DocumentRequirement = (
            apps.get_model(
                "toolkit",
                "DocumentRequirement",
            )
        )

        ProcessStep = (
            apps.get_model(
                "toolkit",
                "ProcessStep",
            )
        )

        # ====================================================
        # HARD SAFETY
        # ====================================================

        if Service.objects.filter(
            status="PUBLISHED"
        ).count() != 163:

            raise RuntimeError(
                "STOP: published Service "
                "count is not 163."
            )

        if (
            KnowledgeDocument.objects.count()
            != 5
        ):

            raise RuntimeError(
                "STOP: expected exactly "
                "5 KnowledgeDocuments."
            )

        if (
            KnowledgeSection.objects.count()
            != 207
        ):

            raise RuntimeError(
                "STOP: expected exactly "
                "207 KnowledgeSections."
            )

        # ====================================================
        # DB BACKUP
        # ====================================================

        db_path = Path(
            settings.DATABASES[
                "default"
            ][
                "NAME"
            ]
        )

        if not db_path.exists():

            raise RuntimeError(
                "STOP: SQLite database "
                "not found."
            )

        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup_path = (
            AUDIT_DIR
            / (
                "before_intelligence_"
                f"knowledge_apply_{stamp}"
                ".sqlite3"
            )
        )

        shutil.copy2(
            db_path,
            backup_path,
        )

        print("")
        print(
            "Database backup:",
            backup_path,
        )

        # ====================================================
        # PREPARE SOURCE SECTIONS
        # ====================================================

        records = []

        skipped_not_bde = 0
        skipped_unlinked = 0
        skipped_blank = 0

        resolution_methods = (
            defaultdict(int)
        )

        for section in (
            KnowledgeSection
            .objects
            .all()
        ):

            if not is_bde_visible(
                section
            ):
                skipped_not_bde += 1
                continue

            service, resolution = (
                resolve_service(
                    section
                )
            )

            if service is None:
                skipped_unlinked += 1
                continue

            if (
                service.status
                != "PUBLISHED"
            ):
                continue

            content = (
                section_content(
                    section
                )
            )

            if not content:
                skipped_blank += 1
                continue

            resolution_methods[
                resolution
            ] += 1

            records.append(
                {
                    "object":
                        section,

                    "service":
                        service,

                    "type":
                        section_type(
                            section
                        ),

                    "title":
                        section_title(
                            section
                        ),

                    "content":
                        content,

                    "order":
                        section_order(
                            section
                        ),

                    "heading":
                        is_heading(
                            section
                        ),

                    "source_row":
                        source_row(
                            section
                        ),
                }
            )

        records.sort(
            key=lambda item: (
                item[
                    "service"
                ].pk,
                item[
                    "order"
                ],
                item[
                    "object"
                ].pk,
            )
        )

        # ====================================================
        # GROUP BY SERVICE
        # ====================================================

        by_service = defaultdict(
            list
        )

        for record in records:

            by_service[
                record["service"].pk
            ].append(record)

        # ====================================================
        # COUNTERS
        # ====================================================

        created_sections = 0
        duplicate_sections = 0

        created_eligibility = 0
        duplicate_eligibility = 0

        created_process = 0
        duplicate_process = 0

        created_documents = 0
        duplicate_documents = 0

        process_candidates_skipped = 0
        document_candidates_skipped = 0

        affected_services = set()

        type_counts = defaultdict(
            int
        )

        # ====================================================
        # APPLY
        # ====================================================

        with transaction.atomic():

            for service_pk, items in (
                by_service.items()
            ):

                service = items[0][
                    "service"
                ]

                # --------------------------------------------
                # Current maximum display orders
                # --------------------------------------------

                content_max = (
                    ServiceContentSection
                    .objects
                    .filter(
                        service=service
                    )
                    .aggregate(
                        value=Max(
                            "display_order"
                        )
                    )[
                        "value"
                    ]
                    or 0
                )

                eligibility_max = (
                    EligibilityRule
                    .objects
                    .filter(
                        service=service
                    )
                    .aggregate(
                        value=Max(
                            "display_order"
                        )
                    )[
                        "value"
                    ]
                    or 0
                )

                process_max = (
                    ProcessStep
                    .objects
                    .filter(
                        service=service
                    )
                    .aggregate(
                        value=Max(
                            "step_number"
                        )
                    )[
                        "value"
                    ]
                    or 0
                )

                document_max = (
                    DocumentRequirement
                    .objects
                    .filter(
                        service=service
                    )
                    .aggregate(
                        value=Max(
                            "display_order"
                        )
                    )[
                        "value"
                    ]
                    or 0
                )

                # --------------------------------------------
                # Track current headings per section type
                # --------------------------------------------

                current_heading = {}

                process_nonheading = [
                    item
                    for item in items
                    if (
                        item["type"]
                        == "PROCESS"
                        and not item[
                            "heading"
                        ]
                    )
                ]

                # --------------------------------------------
                # All knowledge sections
                # --------------------------------------------

                for item in items:

                    content = item[
                        "content"
                    ]

                    sec_type = item[
                        "type"
                    ]

                    title = item[
                        "title"
                    ]

                    heading = item[
                        "heading"
                    ]

                    type_counts[
                        sec_type
                    ] += 1

                    if heading:
                        current_heading[
                            sec_type
                        ] = (
                            title
                            or content
                        )

                    # ========================================
                    # COPY TO BDE CONTENT SECTION
                    # ========================================

                    exists = (
                        ServiceContentSection
                        .objects
                        .filter(
                            service=service,
                            section_type=(
                                sec_type
                            ),
                            content=content,
                        )
                        .exists()
                    )

                    if exists:

                        duplicate_sections += 1

                    else:

                        content_max += 1

                        ServiceContentSection.objects.create(
                            service=service,

                            section_type=(
                                sec_type
                            ),

                            title=trim(
                                ServiceContentSection,
                                "title",
                                title,
                            ),

                            content=content,

                            display_order=(
                                content_max
                            ),

                            visibility="BDE",

                            source_import_row=(
                                item[
                                    "source_row"
                                ]
                            ),
                        )

                        created_sections += 1

                        affected_services.add(
                            service.pk
                        )

                    # ========================================
                    # HEADINGS ARE NOT RULES/STEPS/DOCS
                    # ========================================

                    if heading:
                        continue

                    # ========================================
                    # ELIGIBILITY
                    # ========================================

                    if (
                        sec_type
                        == "ELIGIBILITY"
                    ):

                        rule_type = (
                            eligibility_rule_type(
                                content
                            )
                        )

                        exists = (
                            EligibilityRule
                            .objects
                            .filter(
                                service=service,
                                description=content,
                            )
                            .exists()
                        )

                        if exists:

                            duplicate_eligibility += 1

                        else:

                            eligibility_max += 1

                            EligibilityRule.objects.create(
                                service=service,

                                rule_type=(
                                    rule_type
                                ),

                                title=trim(
                                    EligibilityRule,
                                    "title",
                                    (
                                        current_heading
                                        .get(
                                            "ELIGIBILITY"
                                        )
                                        or
                                        "Eligibility information"
                                    ),
                                ),

                                description=content,

                                display_order=(
                                    eligibility_max
                                ),
                            )

                            created_eligibility += 1

                            affected_services.add(
                                service.pk
                            )

                    # ========================================
                    # PROCESS
                    # ========================================

                    if (
                        sec_type
                        == "PROCESS"
                    ):

                        explicit_items = (
                            split_explicit_list(
                                content
                            )
                        )

                        process_items = []

                        if explicit_items:

                            process_items = (
                                explicit_items
                            )

                        elif (
                            len(
                                process_nonheading
                            )
                            >= 2
                        ):

                            # Multiple source rows under
                            # PROCESS = ordered source steps.
                            process_items = [
                                content
                            ]

                        else:

                            process_candidates_skipped += 1

                        for process_text in (
                            process_items
                        ):

                            # Duplicate by description
                            exists = (
                                ProcessStep
                                .objects
                                .filter(
                                    service=service,
                                    description=(
                                        process_text
                                    ),
                                )
                                .exists()
                            )

                            if exists:

                                duplicate_process += 1
                                continue

                            process_max += 1

                            ProcessStep.objects.create(
                                service=service,

                                step_number=(
                                    process_max
                                ),

                                title=trim(
                                    ProcessStep,
                                    "title",
                                    process_text,
                                ),

                                description=(
                                    process_text
                                ),

                                estimated_time="",
                            )

                            created_process += 1

                            affected_services.add(
                                service.pk
                            )

                    # ========================================
                    # DOCUMENTS
                    # ========================================

                    if (
                        sec_type
                        == "DOCUMENTS"
                    ):

                        heading_text = (
                            current_heading.get(
                                "DOCUMENTS",
                                "",
                            )
                        )

                        mandatory = (
                            documents_are_required(
                                heading_text,
                                content,
                            )
                        )

                        if not mandatory:

                            # Keep it as a BDE content section,
                            # but do not falsely claim mandatory.
                            document_candidates_skipped += 1
                            continue

                        doc_items = (
                            split_explicit_list(
                                content
                            )
                        )

                        if not doc_items:

                            doc_items = [
                                content
                            ]

                        for doc_text in (
                            doc_items
                        ):

                            name = trim(
                                DocumentRequirement,
                                "name",
                                doc_text,
                            )

                            exists = (
                                DocumentRequirement
                                .objects
                                .filter(
                                    service=service,
                                    name=name,
                                )
                                .exists()
                            )

                            if exists:

                                duplicate_documents += 1
                                continue

                            document_max += 1

                            DocumentRequirement.objects.create(
                                service=service,

                                name=name,

                                description=(
                                    doc_text
                                ),

                                is_mandatory=True,

                                display_order=(
                                    document_max
                                ),
                            )

                            created_documents += 1

                            affected_services.add(
                                service.pk
                            )

        # ====================================================
        # REPORT
        # ====================================================

        result = {
            "timestamp":
                datetime.now()
                .isoformat(),

            "backup":
                str(
                    backup_path
                ),

            "source": {
                "knowledge_documents":
                    KnowledgeDocument
                    .objects.count(),

                "knowledge_sections":
                    KnowledgeSection
                    .objects.count(),

                "bde_linked_sections":
                    len(records),

                "not_bde_visible":
                    skipped_not_bde,

                "unlinked":
                    skipped_unlinked,

                "blank":
                    skipped_blank,

                "resolution_methods":
                    dict(
                        resolution_methods
                    ),
            },

            "created": {
                "content_sections":
                    created_sections,

                "eligibility_rules":
                    created_eligibility,

                "process_steps":
                    created_process,

                "document_requirements":
                    created_documents,
            },

            "duplicates": {
                "content_sections":
                    duplicate_sections,

                "eligibility":
                    duplicate_eligibility,

                "process":
                    duplicate_process,

                "documents":
                    duplicate_documents,
            },

            "conservative_skips": {
                "process":
                    process_candidates_skipped,

                "documents":
                    document_candidates_skipped,
            },

            "section_types":
                dict(
                    type_counts
                ),

            "affected_services":
                len(
                    affected_services
                ),

            "final_counts": {
                "published_services":
                    Service
                    .objects
                    .filter(
                        status="PUBLISHED"
                    )
                    .count(),

                "content_sections":
                    ServiceContentSection
                    .objects.count(),

                "eligibility_rules":
                    EligibilityRule
                    .objects.count(),

                "process_steps":
                    ProcessStep
                    .objects.count(),

                "documents":
                    DocumentRequirement
                    .objects.count(),
            },
        }

        report = (
            AUDIT_DIR
            / (
                "intelligence_knowledge_apply_"
                f"{stamp}.json"
            )
        )

        report.write_text(
            json.dumps(
                json_safe(result),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # ====================================================
        # TERMINAL OUTPUT
        # ====================================================

        print("")
        print(
            "===== KNOWLEDGE SOURCE ====="
        )

        print(
            "Knowledge Documents:",
            KnowledgeDocument.objects.count(),
        )

        print(
            "Knowledge Sections:",
            KnowledgeSection.objects.count(),
        )

        print(
            "BDE + Service linked:",
            len(records),
        )

        print(
            "Skipped non-BDE:",
            skipped_not_bde,
        )

        print(
            "Skipped unlinked:",
            skipped_unlinked,
        )

        print("")
        print(
            "===== CREATED FROM KNOWLEDGE ====="
        )

        print(
            "Content Sections:",
            created_sections,
        )

        print(
            "Eligibility Rules:",
            created_eligibility,
        )

        print(
            "Process Steps:",
            created_process,
        )

        print(
            "Document Requirements:",
            created_documents,
        )

        print("")
        print(
            "===== CONSERVATIVE SKIPS ====="
        )

        print(
            "Process prose not safely "
            "structured:",
            process_candidates_skipped,
        )

        print(
            "Documents without explicit "
            "mandatory signal:",
            document_candidates_skipped,
        )

        print("")
        print(
            "===== FINAL COUNTS ====="
        )

        print(
            "Published Services:",
            Service.objects.filter(
                status="PUBLISHED"
            ).count(),
        )

        print(
            "Content Sections:",
            ServiceContentSection
            .objects.count(),
        )

        print(
            "Eligibility Rules:",
            EligibilityRule
            .objects.count(),
        )

        print(
            "Process Steps:",
            ProcessStep
            .objects.count(),
        )

        print(
            "Document Requirements:",
            DocumentRequirement
            .objects.count(),
        )

        print(
            "Affected Services:",
            len(
                affected_services
            ),
        )

        print("")
        print(
            "Report:",
            report,
        )

        print("")
        print("=" * 78)

        print(
            "INTELLIGENCE KNOWLEDGE APPLY: PASS"
        )

        print(
            "NO UNLINKED/ADMIN-ONLY KNOWLEDGE "
            "EXPOSED"
        )

        print(
            "163 PUBLISHED SERVICES PRESERVED"
        )

        print("=" * 78)
