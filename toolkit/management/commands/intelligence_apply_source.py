import json
import shutil

from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from toolkit.intelligence.workbook_intelligence import (
    AUDIT_DIR,
    build_intelligence_plan,
    json_safe,
)


def trim_for_field(model, field_name, value):
    value = str(value or "").strip()

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


class Command(BaseCommand):

    help = (
        "Apply source-backed BharatNXT "
        "intelligence to BDE-safe models."
    )

    def handle(
        self,
        *args,
        **options,
    ):

        print("=" * 76)
        print(
            "BHARATNXT INTELLIGENCE "
            "— SOURCE APPLY"
        )
        print("=" * 76)

        # ====================================================
        # MODELS
        # ====================================================

        Service = apps.get_model(
            "toolkit",
            "Service",
        )

        ImportRow = apps.get_model(
            "toolkit",
            "ImportRow",
        )

        EligibilityRule = apps.get_model(
            "toolkit",
            "EligibilityRule",
        )

        DocumentRequirement = (
            apps.get_model(
                "toolkit",
                "DocumentRequirement",
            )
        )

        ProcessStep = apps.get_model(
            "toolkit",
            "ProcessStep",
        )

        ServiceContentSection = (
            apps.get_model(
                "toolkit",
                "ServiceContentSection",
            )
        )

        # ====================================================
        # SAFETY VALIDATION
        # ====================================================

        if Service.objects.filter(
            status="PUBLISHED"
        ).count() != 163:

            raise RuntimeError(
                "STOP: expected exactly "
                "163 published services."
            )

        visibility_field = (
            ServiceContentSection
            ._meta
            .get_field(
                "visibility"
            )
        )

        visibility_choices = {
            str(value)
            for value, label
            in visibility_field.choices
        }

        if "BDE" not in visibility_choices:

            raise RuntimeError(
                "STOP: BDE visibility "
                "choice unavailable."
            )

        rule_field = (
            EligibilityRule
            ._meta
            .get_field(
                "rule_type"
            )
        )

        rule_choices = {
            str(value)
            for value, label
            in rule_field.choices
        }

        if "INFORMATION" not in rule_choices:

            raise RuntimeError(
                "STOP: INFORMATION "
                "eligibility type unavailable."
            )

        # ====================================================
        # SQLITE BACKUP
        # ====================================================

        db_name = (
            settings.DATABASES[
                "default"
            ][
                "NAME"
            ]
        )

        db_path = Path(db_name)

        if not db_path.exists():

            raise RuntimeError(
                f"STOP: database not found: "
                f"{db_path}"
            )

        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup_path = (
            AUDIT_DIR
            / (
                "before_intelligence_"
                f"source_apply_{stamp}.sqlite3"
            )
        )

        shutil.copy2(
            db_path,
            backup_path,
        )

        print("")
        print(
            "DATABASE BACKUP:",
            backup_path,
        )

        # ====================================================
        # BUILD CURRENT PLAN
        # ====================================================

        print("")
        print(
            "Building current intelligence plan..."
        )

        plan = (
            build_intelligence_plan()
        )

        services_by_pk = {
            service.pk: service
            for service
            in Service.objects
            .filter(
                status="PUBLISHED"
            )
        }

        # ====================================================
        # COUNTERS
        # ====================================================

        created_sections = 0
        skipped_sections = 0

        created_eligibility = 0
        skipped_eligibility = 0

        section_types = {}

        affected_services = set()

        # ====================================================
        # TRANSACTION
        # ====================================================

        with transaction.atomic():

            for service_plan in (
                plan["services"]
            ):

                service = (
                    services_by_pk.get(
                        service_plan[
                            "database_pk"
                        ]
                    )
                )

                if service is None:

                    raise RuntimeError(
                        "Service disappeared "
                        "during intelligence apply."
                    )

                # ============================================
                # CONTENT SECTIONS
                # ============================================

                display_order_by_type = {}

                for candidate in (
                    service_plan[
                        "candidate_sections"
                    ]
                ):

                    section_type = str(
                        candidate.get(
                            "section_type",
                            ""
                        )
                    ).strip()

                    content = str(
                        candidate.get(
                            "content",
                            ""
                        )
                    ).strip()

                    title = str(
                        candidate.get(
                            "title",
                            ""
                        )
                    ).strip()

                    if (
                        not section_type
                        or not content
                    ):
                        continue

                    # Extra safety:
                    # never publish internal/commercial
                    # sections into BDE intelligence.
                    if section_type in {
                        "COMMERCIAL",
                    }:
                        continue

                    section_field = (
                        ServiceContentSection
                        ._meta
                        .get_field(
                            "section_type"
                        )
                    )

                    allowed_sections = {
                        str(value)
                        for value, label
                        in section_field.choices
                    }

                    if (
                        section_type
                        not in allowed_sections
                    ):
                        continue

                    display_order_by_type[
                        section_type
                    ] = (
                        display_order_by_type
                        .get(
                            section_type,
                            0,
                        )
                        + 1
                    )

                    title = trim_for_field(
                        ServiceContentSection,
                        "title",
                        title,
                    )

                    import_row = None

                    import_row_id = (
                        candidate.get(
                            "import_row_id"
                        )
                    )

                    if import_row_id:

                        import_row = (
                            ImportRow.objects
                            .filter(
                                pk=import_row_id
                            )
                            .first()
                        )

                    already_exists = (
                        ServiceContentSection
                        .objects
                        .filter(
                            service=service,
                            section_type=(
                                section_type
                            ),
                            content=content,
                        )
                        .exists()
                    )

                    if already_exists:

                        skipped_sections += 1
                        continue

                    (
                        ServiceContentSection
                        .objects
                        .create(
                            service=service,

                            section_type=(
                                section_type
                            ),

                            title=title,

                            content=content,

                            display_order=(
                                display_order_by_type[
                                    section_type
                                ]
                            ),

                            visibility="BDE",

                            source_import_row=(
                                import_row
                            ),
                        )
                    )

                    created_sections += 1

                    section_types[
                        section_type
                    ] = (
                        section_types.get(
                            section_type,
                            0,
                        )
                        + 1
                    )

                    affected_services.add(
                        service.pk
                    )

                # ============================================
                # ELIGIBILITY
                # ============================================

                eligibility_order = (
                    service
                    .eligibility_rules
                    .count()
                )

                for candidate in (
                    service_plan[
                        "candidate_eligibility"
                    ]
                ):

                    description = str(
                        candidate.get(
                            "description",
                            ""
                        )
                    ).strip()

                    if not description:
                        continue

                    # Do NOT declare extracted prose
                    # a hard requirement yet.
                    # NLP/rule parser will classify later.
                    rule_type = "INFORMATION"

                    title = (
                        "Eligibility information"
                    )

                    title = trim_for_field(
                        EligibilityRule,
                        "title",
                        title,
                    )

                    already_exists = (
                        EligibilityRule.objects
                        .filter(
                            service=service,
                            description=description,
                        )
                        .exists()
                    )

                    if already_exists:

                        skipped_eligibility += 1
                        continue

                    eligibility_order += 1

                    EligibilityRule.objects.create(
                        service=service,

                        rule_type=rule_type,

                        title=title,

                        description=description,

                        display_order=(
                            eligibility_order
                        ),
                    )

                    created_eligibility += 1

                    affected_services.add(
                        service.pk
                    )

        # ====================================================
        # REPORT
        # ====================================================

        result = {
            "generated_at":
                datetime.now()
                .isoformat(),

            "database_backup":
                str(
                    backup_path
                ),

            "published_services":
                Service.objects.filter(
                    status="PUBLISHED"
                ).count(),

            "created": {
                "content_sections":
                    created_sections,

                "eligibility_rules":
                    created_eligibility,

                "documents":
                    0,

                "process_steps":
                    0,
            },

            "skipped_existing": {
                "content_sections":
                    skipped_sections,

                "eligibility_rules":
                    skipped_eligibility,
            },

            "section_types":
                section_types,

            "affected_services":
                len(
                    affected_services
                ),

            "final_database_counts": {
                "content_sections":
                    ServiceContentSection
                    .objects.count(),

                "eligibility_rules":
                    EligibilityRule
                    .objects.count(),

                "documents":
                    DocumentRequirement
                    .objects.count(),

                "process_steps":
                    ProcessStep
                    .objects.count(),
            },

            "source_policy": {
                "invented_information":
                    False,

                "documents_created":
                    False,

                "process_steps_created":
                    False,

                "eligibility_initial_type":
                    "INFORMATION",
            },
        }

        report_path = (
            AUDIT_DIR
            / (
                "intelligence_source_apply_"
                f"{stamp}.json"
            )
        )

        report_path.write_text(
            json.dumps(
                json_safe(result),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # ====================================================
        # OUTPUT
        # ====================================================

        print("")
        print(
            "===== CREATED ====="
        )

        print(
            "Content sections:",
            created_sections,
        )

        print(
            "Eligibility rules:",
            created_eligibility,
        )

        print(
            "Documents:",
            0,
        )

        print(
            "Process steps:",
            0,
        )

        print("")
        print(
            "===== SECTION TYPES ====="
        )

        for key in sorted(
            section_types
        ):

            print(
                f"{key}: "
                f"{section_types[key]}"
            )

        print("")
        print(
            "===== FINAL COUNTS ====="
        )

        print(
            "Content sections:",
            ServiceContentSection
            .objects.count(),
        )

        print(
            "Eligibility rules:",
            EligibilityRule
            .objects.count(),
        )

        print(
            "Documents:",
            DocumentRequirement
            .objects.count(),
        )

        print(
            "Process steps:",
            ProcessStep
            .objects.count(),
        )

        print(
            "Affected services:",
            len(
                affected_services
            ),
        )

        print("")
        print(
            "Report:",
            report_path,
        )

        print("")
        print("=" * 76)
        print(
            "INTELLIGENCE SOURCE APPLY: PASS"
        )
        print(
            "163 PUBLISHED SERVICES PRESERVED"
        )
        print(
            "NO DOCUMENT/PROCESS DATA INVENTED"
        )
        print("=" * 76)
