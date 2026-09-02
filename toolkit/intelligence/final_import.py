"""
BharatNXT Wave
Final Import Engine V1

Safety:
- approved changes only
- atomic transaction
- SQLite backup before mutation
- duplicate SHA protection
- existing Service classification preserved
- blank/weaker values never overwrite existing values
- ImportChange audit
- reversible created/updated objects
"""

import os
import shutil
import sqlite3
import subprocess
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

from toolkit.intelligence.delta import (
    classify_candidate,
    normalize_text,
    normalize_url,
)


ENGINE_VERSION = "FINAL_IMPORT_V1"


class FinalImportError(Exception):
    pass


class DuplicateSourceError(FinalImportError):
    pass


def _model(name):
    try:
        return apps.get_model(
            "toolkit",
            name,
        )
    except LookupError:
        return None


Service = _model("Service")
Category = _model("Category")
ImportBatch = _model("ImportBatch")
ImportRow = _model("ImportRow")
ImportChange = _model("ImportChange")
ServiceContentSection = _model(
    "ServiceContentSection"
)
ServiceCommercial = _model(
    "ServiceCommercial"
)
ServiceSource = _model(
    "ServiceSource"
)


# ============================================================
# GENERIC HELPERS
# ============================================================

def _json_safe(value):

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        Decimal,
    ):
        return str(value)

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _json_safe(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    return str(value)


def _snapshot(instance):

    result = {}

    for field in (
        instance._meta.concrete_fields
    ):

        if field.primary_key:
            continue

        try:
            value = getattr(
                instance,
                field.attname,
            )
        except Exception:
            continue

        result[
            field.attname
        ] = _json_safe(
            value
        )

    return result


def _restore_snapshot(
    instance,
    snapshot,
):

    for field in (
        instance._meta.concrete_fields
    ):

        if field.primary_key:
            continue

        key = field.attname

        if key not in snapshot:
            continue

        value = snapshot[
            key
        ]

        try:

            if (
                value is not None
                and not field.is_relation
            ):
                value = (
                    field.to_python(
                        value
                    )
                )

        except Exception:
            pass

        setattr(
            instance,
            key,
            value,
        )

    instance.save()


def _field_names(Model):

    if Model is None:
        return set()

    return {
        field.name
        for field
        in Model._meta.fields
    }


def _field(
    Model,
    name,
):

    if Model is None:
        return None

    try:
        return Model._meta.get_field(
            name
        )
    except Exception:
        return None


def _pick_field(
    Model,
    *names,
):

    existing = _field_names(
        Model
    )

    for name in names:
        if name in existing:
            return name

    return None


def _choice_value(
    Model,
    field_name,
    preferred,
):

    field = _field(
        Model,
        field_name,
    )

    if field is None:
        return None

    choices = {
        str(value)
        for value, label
        in (
            field.choices
            or []
        )
    }

    if not choices:
        return preferred

    if preferred in choices:
        return preferred

    return None


def _required_check(
    Model,
    kwargs,
):

    missing = []

    for field in (
        Model._meta.concrete_fields
    ):

        if (
            field.primary_key
            or field.auto_created
            or getattr(
                field,
                "auto_now",
                False,
            )
            or getattr(
                field,
                "auto_now_add",
                False,
            )
        ):
            continue

        if (
            field.name in kwargs
            or field.attname in kwargs
        ):
            continue

        if (
            field.null
            or field.has_default()
        ):
            continue

        # Empty strings are valid database values for
        # optional textual metadata even when form blank=False.
        if isinstance(
            field,
            (
                models.CharField,
                models.TextField,
            ),
        ):
            kwargs[
                field.name
            ] = ""
            continue

        missing.append(
            field.name
        )

    if missing:
        raise FinalImportError(
            f"Cannot safely create "
            f"{Model.__name__}; required "
            f"fields are unknown: "
            f"{', '.join(missing)}"
        )


def _record_change(
    batch,
    row,
    service,
    action,
    instance,
    before=None,
    after=None,
):

    ImportChange.objects.create(
        import_batch=batch,
        import_row=row,
        service=service,
        action=action,
        object_model=(
            instance._meta.label
            if instance
            else ""
        ),
        object_pk=(
            str(instance.pk)
            if instance
            and instance.pk is not None
            else ""
        ),
        before_snapshot=(
            before
            or {}
        ),
        after_snapshot=(
            after
            or {}
        ),
    )


def _review(row):

    raw = (
        row.raw_data
        if isinstance(
            row.raw_data,
            dict,
        )
        else {}
    )

    review = raw.get(
        "review",
        {},
    )

    if not isinstance(
        review,
        dict,
    ):
        review = {}

    return review


def _candidate(row):

    raw = (
        row.raw_data
        if isinstance(
            row.raw_data,
            dict,
        )
        else {}
    )

    candidate = raw.get(
        "candidate",
        {},
    )

    if not isinstance(
        candidate,
        dict,
    ):
        return {}

    return candidate


def _decision(row):

    if (
        row.candidate_action
        == "SKIP"
    ):
        return "SKIPPED"

    return str(
        _review(row).get(
            "decision",
            "PENDING",
        )
        or "PENDING"
    ).upper()


# ============================================================
# DATABASE BACKUP
# ============================================================

def _backup_directory():
    """Where pre-import snapshots are written."""

    directory = Path(
        getattr(
            settings,
            "BNW_IMPORT_BACKUP_ROOT",
            Path(settings.BASE_DIR)
            / "confidential_source"
            / "audit",
        )
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


def _backup_sqlite(db, destination):
    source = Path(db["NAME"])

    if not source.exists():
        raise FinalImportError(
            f"SQLite database not found: {source}"
        )

    source_connection = sqlite3.connect(str(source))
    destination_connection = sqlite3.connect(str(destination))

    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _backup_postgresql(db, destination):
    """Snapshot via pg_dump, matching deployment/backup_database.sh."""

    if not shutil.which("pg_dump"):
        raise FinalImportError(
            "pg_dump was not found on PATH. It is required to take the "
            "pre-import safety backup. Install the PostgreSQL client "
            "tools on the application server."
        )

    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--host", str(db.get("HOST") or "127.0.0.1"),
        "--port", str(db.get("PORT") or "5432"),
        "--username", str(db.get("USER") or ""),
        "--file", str(destination),
        str(db["NAME"]),
    ]

    environment = os.environ.copy()

    # Passed by environment rather than on the command line, so it does not
    # appear in the process list or in any error text below.
    if db.get("PASSWORD"):
        environment["PGPASSWORD"] = str(db["PASSWORD"])

    try:
        subprocess.run(
            command,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as exc:
        raise FinalImportError(
            "pg_dump failed while taking the pre-import backup: "
            f"{(exc.stderr or '').strip()}"
        ) from exc


def backup_database(batch_id):
    """Take a full database snapshot before an import is applied.

    Both SQLite (development) and PostgreSQL (production) are supported.
    This used to raise on any non-SQLite engine, which made apply_batch and
    rollback_batch - the whole Final Import feature - unusable on the
    production database.
    """

    db = settings.DATABASES["default"]
    engine = db.get("ENGINE", "")

    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    directory = _backup_directory()

    if engine == "django.db.backends.sqlite3":
        destination = directory / (
            f"before_final_import_batch{batch_id}_{stamp}.sqlite3"
        )

        _backup_sqlite(db, destination)

    elif engine == "django.db.backends.postgresql":
        destination = directory / (
            f"before_final_import_batch{batch_id}_{stamp}.dump"
        )

        _backup_postgresql(db, destination)

    else:
        raise FinalImportError(
            f"Automatic Final Import backup does not support the "
            f"database engine {engine!r}. Supported engines are SQLite "
            f"and PostgreSQL."
        )

    return str(destination)


# ============================================================
# DUPLICATE SOURCE SAFETY
# ============================================================

def duplicate_imported_batch(
    batch,
):

    if not batch.file_sha256:
        return None

    return (
        ImportBatch.objects
        .filter(
            file_sha256=(
                batch.file_sha256
            ),
            status="IMPORTED",
        )
        .exclude(
            pk=batch.pk
        )
        .order_by(
            "-imported_at",
            "-created_at",
        )
        .first()
    )


# ============================================================
# CONTENT MATERIALISATION
# ============================================================

SECTION_MAP = {
    "benefits":
        "BENEFITS",

    "eligibility":
        "ELIGIBILITY",

    "applicable_for":
        "ELIGIBILITY",

    "focus_sectors":
        "SCOPE",

    "funding_organisation":
        "FUNDING",

    "funding_type":
        "FUNDING",

    "scheme_type":
        "FUNDING",

    "deadline":
        "TIMELINE",

    "additional_info":
        "NOTES",

    "commercial_remark":
        "COMMERCIAL",
}


CORE_FIELD_MAP = {
    "benefits":
        "benefits",

    "eligibility":
        "eligibility_summary",

    "applicable_for":
        "applicable_for_raw",

    "funding_organisation":
        "funding_organisation",

    "funding_type":
        "funding_type",

    "scheme_type":
        "funding_type",

    "deadline":
        "application_deadline_raw",

    "additional_info":
        "important_notes",
}


COMMERCIAL_FIELDS = {
    "minimum_charge",
    "government_charge",
    "government_fee",
    "vendor_cost",
    "bdm_deduction",
    "commercial_remark",
}


LINK_FIELDS = {
    "portal_link",
    "application_link",
    "official_link",
    "reference_link",
    "flyer",
}


def _content_text_field():

    return _pick_field(
        ServiceContentSection,
        "content",
        "body",
        "text",
        "details",
        "value",
    )


def _content_exists(
    service,
    content,
):

    if ServiceContentSection is None:
        return False

    content_field = (
        _content_text_field()
    )

    if not content_field:
        return False

    service_field = _pick_field(
        ServiceContentSection,
        "service",
    )

    if not service_field:
        return False

    normalized = normalize_text(
        content
    )

    if not normalized:
        return True

    queryset = (
        ServiceContentSection.objects
        .filter(
            **{
                service_field:
                    service
            }
        )
    )

    for obj in queryset:

        existing = normalize_text(
            getattr(
                obj,
                content_field,
                "",
            )
        )

        if existing == normalized:
            return True

    return False


def _create_content(
    batch,
    row,
    service,
    section_type,
    content,
    heading=None,
):

    content = str(
        content or ""
    ).strip()

    if not content:
        return None

    if _content_exists(
        service,
        content,
    ):
        return None

    if ServiceContentSection is None:
        raise FinalImportError(
            "ServiceContentSection model "
            "is unavailable."
        )

    service_field = _pick_field(
        ServiceContentSection,
        "service",
    )

    content_field = (
        _content_text_field()
    )

    if (
        not service_field
        or not content_field
    ):
        raise FinalImportError(
            "ServiceContentSection model "
            "does not expose expected "
            "service/content fields."
        )

    kwargs = {
        service_field:
            service,

        content_field:
            content,
    }

    section_field = _pick_field(
        ServiceContentSection,
        "section_type",
        "content_type",
        "kind",
    )

    if section_field:

        value = _choice_value(
            ServiceContentSection,
            section_field,
            section_type,
        )

        if value is None:
            value = _choice_value(
                ServiceContentSection,
                section_field,
                "OTHER",
            )

        if value is not None:
            kwargs[
                section_field
            ] = value

    visibility_field = _pick_field(
        ServiceContentSection,
        "visibility",
    )

    if visibility_field:

        value = _choice_value(
            ServiceContentSection,
            visibility_field,
            "BDE",
        )

        if value is not None:
            kwargs[
                visibility_field
            ] = value

    title_field = _pick_field(
        ServiceContentSection,
        "title",
        "heading",
        "label",
    )

    if title_field:

        kwargs[
            title_field
        ] = (
            heading
            or section_type.replace(
                "_",
                " ",
            ).title()
        )

    source_row_field = (
        _pick_field(
            ServiceContentSection,
            "source_import_row",
            "import_row",
        )
    )

    if source_row_field:

        kwargs[
            source_row_field
        ] = row

    source_sheet_field = (
        _pick_field(
            ServiceContentSection,
            "source_sheet",
            "sheet_name",
        )
    )

    if source_sheet_field:

        kwargs[
            source_sheet_field
        ] = row.sheet_name

    row_number_field = (
        _pick_field(
            ServiceContentSection,
            "source_row_number",
        )
    )

    if row_number_field:

        kwargs[
            row_number_field
        ] = (
            row.source_row_number
        )

    _required_check(
        ServiceContentSection,
        kwargs,
    )

    obj = (
        ServiceContentSection.objects
        .create(
            **kwargs
        )
    )

    _record_change(
        batch,
        row,
        service,
        "CONTENT_CREATE",
        obj,
        before={},
        after=_snapshot(obj),
    )

    return obj


# ============================================================
# SERVICE CORE FIELDS
# ============================================================

def _safe_core_addition(
    batch,
    row,
    service,
    incoming_field,
    value,
):

    target = CORE_FIELD_MAP.get(
        incoming_field
    )

    if not target:
        return False

    field = _field(
        Service,
        target,
    )

    if field is None:
        return False

    # Do not push arbitrary strings into JSON,
    # relational, numeric or date fields.
    if not isinstance(
        field,
        (
            models.CharField,
            models.TextField,
        ),
    ):
        return False

    existing = getattr(
        service,
        target,
        "",
    )

    if normalize_text(
        existing
    ):
        return False

    value = str(
        value or ""
    ).strip()

    if not value:
        return True

    before = _snapshot(
        service
    )

    setattr(
        service,
        target,
        value,
    )

    service.save(
        update_fields=[
            target
        ]
    )

    after = _snapshot(
        service
    )

    _record_change(
        batch,
        row,
        service,
        "SERVICE_UPDATE",
        service,
        before=before,
        after=after,
    )

    return True


# ============================================================
# AUTOMATIC STRUCTURED ELIGIBILITY
# ============================================================

def _apply_structured_eligibility(
    batch,
    row,
    service,
):
    """
    AUTO_STRUCTURED_ELIGIBILITY_IMPORT_V1

    Run the proven Structured Eligibility V1 extractor after
    approved Service/content materialisation.

    Safety:
    - only fills currently-empty structured fields;
    - never overwrites existing structured values;
    - records one normal SERVICE_UPDATE ImportChange;
    - existing batch rollback restores the before snapshot.
    """

    from toolkit.eligibility_extraction import (
        extract_service,
    )


    proposal, source_text = (
        extract_service(
            service
        )
    )


    list_fields = (
        "business_types",
        "business_stages",
        "industries",
        "applicable_states",
        "founder_categories",
    )


    scalar_fields = (
        "min_business_age_months",
        "max_business_age_months",
        "min_turnover",
        "max_turnover",
    )


    changed_fields = []


    # --------------------------------------------------------
    # LIST / JSON FIELDS
    # --------------------------------------------------------

    for field_name in list_fields:

        if not hasattr(
            service,
            field_name,
        ):

            continue


        current = getattr(
            service,
            field_name,
        )


        proposed = proposal.get(
            field_name
        )


        if (
            not current
            and proposed
        ):

            changed_fields.append(
                field_name
            )


    # --------------------------------------------------------
    # NUMERIC FIELDS
    # --------------------------------------------------------

    for field_name in scalar_fields:

        if not hasattr(
            service,
            field_name,
        ):

            continue


        current = getattr(
            service,
            field_name,
        )


        proposed = proposal.get(
            field_name
        )


        if (
            current is None
            and proposed is not None
        ):

            changed_fields.append(
                field_name
            )


    if not changed_fields:

        return []


    # Snapshot BEFORE changing anything.
    before = _snapshot(
        service
    )


    for field_name in changed_fields:

        setattr(
            service,
            field_name,
            proposal[
                field_name
            ],
        )


    service.save(
        update_fields=changed_fields
    )


    after = _snapshot(
        service
    )


    # Use the EXISTING import rollback mechanism.
    _record_change(
        batch,
        row,
        service,
        "SERVICE_UPDATE",
        service,
        before=before,
        after=after,
    )


    return changed_fields



# ============================================================
# SERVICE SOURCES / LINKS
# ============================================================

def _create_source(
    batch,
    row,
    service,
    field_name,
    url,
):

    if ServiceSource is None:
        return None

    url = normalize_url(
        url
    )

    if not url:
        return None

    service_field = _pick_field(
        ServiceSource,
        "service",
    )

    url_field = _pick_field(
        ServiceSource,
        "source_url",
        "url",
    )

    if (
        not service_field
        or not url_field
    ):
        return None

    queryset = (
        ServiceSource.objects
        .filter(
            **{
                service_field:
                    service
            }
        )
    )

    for existing in queryset:

        if normalize_url(
            getattr(
                existing,
                url_field,
                "",
            )
        ) == url:

            return None

    kwargs = {
        service_field:
            service,

        url_field:
            url,
    }

    name_field = _pick_field(
        ServiceSource,
        "source_name",
        "name",
        "title",
    )

    if name_field:
        kwargs[
            name_field
        ] = (
            str(
                field_name
            )
            .replace(
                "_",
                " ",
            )
            .title()
        )

    kind_field = _pick_field(
        ServiceSource,
        "source_kind",
        "kind",
        "source_type",
    )

    kind_map = {
        "portal_link":
            "OFFICIAL_PORTAL",

        "official_link":
            "OFFICIAL_PORTAL",

        "application_link":
            "APPLICATION",

        "flyer":
            "FLYER",

        "reference_link":
            "REFERENCE",
    }

    if kind_field:

        preferred = kind_map.get(
            field_name,
            "REFERENCE",
        )

        value = _choice_value(
            ServiceSource,
            kind_field,
            preferred,
        )

        if value is not None:
            kwargs[
                kind_field
            ] = value

    import_row_field = (
        _pick_field(
            ServiceSource,
            "source_import_row",
            "import_row",
        )
    )

    if import_row_field:
        kwargs[
            import_row_field
        ] = row

    reference_field = _pick_field(
        ServiceSource,
        "source_reference",
        "reference",
    )

    if reference_field:
        kwargs[
            reference_field
        ] = (
            f"{row.sheet_name} "
            f"row "
            f"{row.source_row_number}"
        )

    _required_check(
        ServiceSource,
        kwargs,
    )

    obj = (
        ServiceSource.objects
        .create(
            **kwargs
        )
    )

    _record_change(
        batch,
        row,
        service,
        "SOURCE_ADD",
        obj,
        before={},
        after=_snapshot(obj),
    )

    return obj


# ============================================================
# COMMERCIAL DATA
# ============================================================

COMMERCIAL_MODEL_MAP = {
    "minimum_charge":
        "minimum_charge_raw",

    "government_charge":
        "government_fee_raw",

    "government_fee":
        "government_fee_raw",

    "vendor_cost":
        "vendor_cost_raw",

    "bdm_deduction":
        "bdm_deduction_raw",

    "commercial_remark":
        "remarks",
}


def _create_commercial(
    batch,
    row,
    service,
    values,
):

    if (
        ServiceCommercial is None
        or not values
    ):
        return None

    service_field = _pick_field(
        ServiceCommercial,
        "service",
    )

    if not service_field:
        return None

    kwargs = {
        service_field:
            service,
    }

    for source_name, raw_value in (
        values.items()
    ):

        target = (
            COMMERCIAL_MODEL_MAP.get(
                source_name
            )
        )

        if (
            target
            and target
            in _field_names(
                ServiceCommercial
            )
        ):

            kwargs[
                target
            ] = str(
                raw_value or ""
            ).strip()

    visibility_field = _pick_field(
        ServiceCommercial,
        "visibility",
    )

    if visibility_field:

        value = _choice_value(
            ServiceCommercial,
            visibility_field,
            "BDE_ALLOWED",
        )

        if value is not None:
            kwargs[
                visibility_field
            ] = value

    import_row_field = (
        _pick_field(
            ServiceCommercial,
            "source_import_row",
            "import_row",
        )
    )

    if import_row_field:
        kwargs[
            import_row_field
        ] = row

    # Do not create an empty commercial record.
    meaningful = {
        key:
            value
        for key, value
        in kwargs.items()
        if key not in {
            service_field,
            import_row_field,
            visibility_field,
        }
        and normalize_text(
            value
        )
    }

    if not meaningful:
        return None

    # Exact dedupe.
    for existing in (
        ServiceCommercial.objects
        .filter(
            **{
                service_field:
                    service
            }
        )
    ):

        same = True

        for key, value in meaningful.items():

            if normalize_text(
                getattr(
                    existing,
                    key,
                    "",
                )
            ) != normalize_text(
                value
            ):

                same = False
                break

        if same:
            return None

    _required_check(
        ServiceCommercial,
        kwargs,
    )

    obj = (
        ServiceCommercial.objects
        .create(
            **kwargs
        )
    )

    _record_change(
        batch,
        row,
        service,
        "COMMERCIAL_CREATE",
        obj,
        before={},
        after=_snapshot(obj),
    )

    return obj


# ============================================================
# DIFFERENCE APPLICATION
# ============================================================

def _apply_difference(
    batch,
    row,
    service,
    difference,
):

    field_name = str(
        difference.get(
            "field",
            "",
        )
    )

    value = difference.get(
        "incoming"
    )

    change_type = str(
        difference.get(
            "change_type",
            "",
        )
    )

    if change_type not in {
        "SAFE_ADDITION",
    }:

        raise FinalImportError(
            f"Field '{field_name}' is "
            f"{change_type}; automatic "
            "overwrite is intentionally blocked."
        )

    # Narrative section.
    if field_name.startswith(
        "section:"
    ):

        section_type = (
            field_name.split(
                ":",
                1,
            )[1]
            or "OTHER"
        )

        _create_content(
            batch,
            row,
            service,
            section_type,
            value,
        )

        return

    # Narrative/source link.
    if field_name.startswith(
        "link:"
    ):

        _create_source(
            batch,
            row,
            service,
            "reference_link",
            value,
        )

        return

    if field_name in LINK_FIELDS:

        _create_source(
            batch,
            row,
            service,
            field_name,
            value,
        )

        return

    if field_name in COMMERCIAL_FIELDS:

        _create_commercial(
            batch,
            row,
            service,
            {
                field_name:
                    value
            },
        )

        return

    # Safely fill a blank Service core field.
    if _safe_core_addition(
        batch,
        row,
        service,
        field_name,
        value,
    ):
        return

    # Otherwise preserve it as structured BDE content.
    section_type = SECTION_MAP.get(
        field_name,
        "OTHER",
    )

    _create_content(
        batch,
        row,
        service,
        section_type,
        value,
        heading=(
            field_name
            .replace(
                "_",
                " ",
            )
            .title()
        ),
    )


def _apply_candidate_links(
    batch,
    row,
    service,
    candidate,
):

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

        _create_source(
            batch,
            row,
            service,
            str(
                link.get(
                    "field",
                    "reference_link",
                )
            ),
            link.get(
                "url"
            ),
        )


# ============================================================
# NEW SERVICE CREATION
# ============================================================

def _unique_slug(
    title,
):

    base = (
        slugify(
            title
        )
        or "imported-service"
    )[:240]

    candidate = base
    number = 2

    while Service.objects.filter(
        slug=candidate
    ).exists():

        suffix = f"-{number}"

        candidate = (
            base[
                :240 - len(
                    suffix
                )
            ]
            + suffix
        )

        number += 1

    return candidate


def _unique_service_id(
    batch,
    row,
):

    base = (
        f"BNXT-IMP-"
        f"{batch.pk}-"
        f"{row.pk}"
    )[:40]

    candidate = base
    number = 2

    while Service.objects.filter(
        service_id=candidate
    ).exists():

        suffix = (
            f"-{number}"
        )

        candidate = (
            base[
                :40 - len(
                    suffix
                )
            ]
            + suffix
        )

        number += 1

    return candidate


def _create_service(
    batch,
    row,
    candidate,
):

    review = _review(
        row
    )

    category_id = (
        review.get(
            "category_id"
        )
    )

    service_kind = str(
        review.get(
            "service_kind",
            "",
        )
    ).strip()

    if not category_id:
        raise FinalImportError(
            f"Row {row.pk}: new Service "
            "has no approved category."
        )

    category = (
        Category.objects
        .select_related(
            "domain"
        )
        .filter(
            pk=category_id
        )
        .first()
    )

    if category is None:
        raise FinalImportError(
            f"Row {row.pk}: selected "
            "category no longer exists."
        )

    valid_kinds = {
        value
        for value, label
        in Service.SERVICE_KIND_CHOICES
    }

    if service_kind not in valid_kinds:
        raise FinalImportError(
            f"Row {row.pk}: invalid "
            f"Service kind "
            f"'{service_kind}'."
        )

    title = str(
        candidate.get(
            "title",
            "",
        )
    ).strip()

    if not title:
        raise FinalImportError(
            f"Row {row.pk}: Service title "
            "is empty."
        )

    kwargs = {
        "service_id":
            _unique_service_id(
                batch,
                row,
            ),

        "title":
            title,

        "slug":
            _unique_slug(
                title
            ),

        "domain":
            category.domain,

        "category":
            category,

        "service_kind":
            service_kind,

        "status":
            "PUBLISHED",
    }

    _required_check(
        Service,
        kwargs,
    )

    service = (
        Service.objects.create(
            **kwargs
        )
    )

    _record_change(
        batch,
        row,
        service,
        "SERVICE_CREATE",
        service,
        before={},
        after=_snapshot(
            service
        ),
    )

    return service


# ============================================================
# PREVIEW
# ============================================================

def preview_batch(
    batch_id,
):

    batch = (
        ImportBatch.objects
        .get(
            pk=batch_id
        )
    )

    duplicate = (
        duplicate_imported_batch(
            batch
        )
    )

    counts = Counter()

    approved = 0
    skipped = 0
    pending = 0

    rows = (
        ImportRow.objects
        .filter(
            import_batch=batch
        )
        .select_related(
            "matched_service"
        )
        .order_by(
            "sheet_name",
            "source_row_number",
        )
    )

    candidate_rows = 0

    for row in rows:

        candidate = _candidate(
            row
        )

        if not candidate:
            continue

        candidate_rows += 1

        delta = classify_candidate(
            candidate
        )

        status = delta.get(
            "status",
            "CONFLICT",
        )

        counts[
            status
        ] += 1

        decision = _decision(
            row
        )

        if decision == "APPROVED":
            approved += 1

        elif decision == "SKIPPED":
            skipped += 1

        elif status != "NO_CHANGE":
            pending += 1

    return {
        "batch_id":
            batch.pk,

        "status":
            batch.status,

        "candidate_rows":
            candidate_rows,

        "delta_counts":
            dict(counts),

        "approved":
            approved,

        "skipped":
            skipped,

        "pending_changes":
            pending,

        "duplicate":
            bool(
                duplicate
            ),

        "duplicate_of":
            (
                duplicate.pk
                if duplicate
                else None
            ),
    }


# ============================================================
# FINAL APPLY
# ============================================================

def apply_batch(
    batch_id,
    *,
    user=None,
    reconcile=False,
):

    batch = (
        ImportBatch.objects
        .get(
            pk=batch_id
        )
    )

    if batch.status not in {
        "PREVIEWED",
        "VALIDATED",
    }:
        raise FinalImportError(
            f"Batch #{batch.pk} has status "
            f"{batch.status}; cannot import."
        )

    duplicate = (
        duplicate_imported_batch(
            batch
        )
    )

    if (
        duplicate
        and not reconcile
    ):
        raise DuplicateSourceError(
            f"Batch #{batch.pk} is an exact "
            f"duplicate of imported batch "
            f"#{duplicate.pk}."
        )

    preview = preview_batch(
        batch.pk
    )

    if (
        preview[
            "pending_changes"
        ]
        > 0
    ):
        raise FinalImportError(
            f"{preview['pending_changes']} "
            "change candidate(s) still need "
            "Approve or Skip."
        )

    if reconcile:

        forbidden = (
            preview[
                "delta_counts"
            ].get(
                "CHANGED_INFORMATION",
                0,
            )
            + preview[
                "delta_counts"
            ].get(
                "CONFLICT",
                0,
            )
            + preview[
                "delta_counts"
            ].get(
                "NEW_SERVICE",
                0,
            )
        )

        if forbidden:
            raise FinalImportError(
                "Reconciliation mode allows "
                "only NO_CHANGE and "
                "SAFE_ADDITION."
            )

    backup_path = (
        backup_database(
            batch.pk
        )
    )

    processed = 0
    created_services = 0
    changed_objects_before = (
        ImportChange.objects
        .filter(
            import_batch=batch
        )
        .count()
    )

    try:

        with transaction.atomic():

            locked_batch = (
                ImportBatch.objects
                .select_for_update()
                .get(
                    pk=batch.pk
                )
            )

            locked_batch.status = (
                "IMPORTING"
            )

            locked_batch.save(
                update_fields=[
                    "status"
                ]
            )

            rows = (
                ImportRow.objects
                .select_for_update()
                .filter(
                    import_batch=(
                        locked_batch
                    )
                )
                .select_related(
                    "matched_service"
                )
                .order_by(
                    "sheet_name",
                    "source_row_number",
                )
            )

            for row in rows:

                candidate = (
                    _candidate(
                        row
                    )
                )

                if not candidate:
                    continue

                delta = (
                    classify_candidate(
                        candidate
                    )
                )

                status = delta.get(
                    "status"
                )

                decision = (
                    _decision(
                        row
                    )
                )

                # Source row contains no new information.
                if status == "NO_CHANGE":

                    service_id = (
                        delta.get(
                            "matched_service_id"
                        )
                    )

                    if service_id:
                        row.imported_service_id = (
                            service_id
                        )

                    row.validation_status = (
                        "PROCESSED"
                    )

                    row.processed_at = (
                        timezone.now()
                    )

                    row.save(
                        update_fields=[
                            "imported_service",
                            "validation_status",
                            "processed_at",
                        ]
                    )

                    processed += 1
                    continue

                if decision == "SKIPPED":

                    row.validation_status = (
                        "PROCESSED"
                    )

                    row.processed_at = (
                        timezone.now()
                    )

                    row.save(
                        update_fields=[
                            "validation_status",
                            "processed_at",
                        ]
                    )

                    processed += 1
                    continue

                if decision != "APPROVED":
                    raise FinalImportError(
                        f"Row {row.pk} is "
                        "not approved."
                    )

                if status == "CONFLICT":

                    raise FinalImportError(
                        f"Row {row.pk} is still "
                        "a conflict."
                    )

                if status == "CHANGED_INFORMATION":

                    raise FinalImportError(
                        f"Row {row.pk} contains "
                        "replacement information. "
                        "Automatic overwrite is "
                        "blocked in V1."
                    )

                if status == "NEW_SERVICE":

                    service = (
                        _create_service(
                            locked_batch,
                            row,
                            candidate,
                        )
                    )

                    created_services += 1

                    # Materialise all structured
                    # fields as safe incoming data.
                    fields = (
                        candidate.get(
                            "fields",
                            {},
                        )
                        or {}
                    )

                    commercial = {}

                    for (
                        field_name,
                        value,
                    ) in fields.items():

                        if field_name in {
                            "scheme_name",
                            "service_name",
                            "title",
                        }:
                            continue

                        if (
                            field_name
                            in COMMERCIAL_FIELDS
                        ):
                            commercial[
                                field_name
                            ] = value
                            continue

                        if (
                            field_name
                            in LINK_FIELDS
                        ):
                            continue

                        if not _safe_core_addition(
                            locked_batch,
                            row,
                            service,
                            field_name,
                            value,
                        ):

                            _create_content(
                                locked_batch,
                                row,
                                service,
                                SECTION_MAP.get(
                                    field_name,
                                    "OTHER",
                                ),
                                value,
                                heading=(
                                    field_name
                                    .replace(
                                        "_",
                                        " ",
                                    )
                                    .title()
                                ),
                            )

                    _create_commercial(
                        locked_batch,
                        row,
                        service,
                        commercial,
                    )

                    for section in (
                        candidate.get(
                            "sections",
                            [],
                        )
                        or []
                    ):

                        if not isinstance(
                            section,
                            dict,
                        ):
                            continue

                        _create_content(
                            locked_batch,
                            row,
                            service,
                            str(
                                section.get(
                                    "section_type",
                                    "OTHER",
                                )
                            ),
                            section.get(
                                "content"
                            ),
                        )

                    _apply_candidate_links(
                        locked_batch,
                        row,
                        service,
                        candidate,
                    )

                else:

                    service_id = (
                        delta.get(
                            "matched_service_id"
                        )
                    )

                    service = (
                        Service.objects
                        .select_for_update()
                        .get(
                            pk=service_id
                        )
                    )

                    # Existing Service classification
                    # remains untouched here.
                    for difference in (
                        delta.get(
                            "differences",
                            []
                        )
                    ):

                        _apply_difference(
                            locked_batch,
                            row,
                            service,
                            difference,
                        )

                    _apply_candidate_links(
                        locked_batch,
                        row,
                        service,
                        candidate,
                    )

                _apply_structured_eligibility(
                    locked_batch,
                    row,
                    service,
                )

                row.imported_service = (
                    service
                )

                row.validation_status = (
                    "PROCESSED"
                )

                row.processed_at = (
                    timezone.now()
                )

                row.save(
                    update_fields=[
                        "imported_service",
                        "validation_status",
                        "processed_at",
                    ]
                )

                processed += 1

            metadata = (
                dict(
                    locked_batch.metadata
                    or {}
                )
            )

            metadata[
                "final_import"
            ] = {
                "engine":
                    ENGINE_VERSION,

                "backup":
                    backup_path,

                "reconcile":
                    bool(
                        reconcile
                    ),

                "duplicate_of":
                    (
                        duplicate.pk
                        if duplicate
                        else None
                    ),

                "processed_candidates":
                    processed,
            }

            locked_batch.metadata = (
                metadata
            )

            locked_batch.status = (
                "IMPORTED"
            )

            locked_batch.imported_at = (
                timezone.now()
            )

            if user is not None:
                locked_batch.imported_by = (
                    user
                )

            update_fields = [
                "metadata",
                "status",
                "imported_at",
            ]

            if user is not None:
                update_fields.append(
                    "imported_by"
                )

            locked_batch.save(
                update_fields=(
                    update_fields
                )
            )

    except Exception:

        ImportBatch.objects.filter(
            pk=batch.pk
        ).update(
            status="FAILED"
        )

        raise

    changes_after = (
        ImportChange.objects
        .filter(
            import_batch_id=batch.pk
        )
        .count()
    )

    return {
        "batch_id":
            batch.pk,

        "backup":
            backup_path,

        "processed":
            processed,

        "created_services":
            created_services,

        "changes_created":
            (
                changes_after
                - changed_objects_before
            ),

        "status":
            "IMPORTED",
    }


# ============================================================
# ROLLBACK
# ============================================================

def rollback_batch(
    batch_id,
    *,
    user=None,
):

    batch = (
        ImportBatch.objects
        .get(
            pk=batch_id
        )
    )

    if batch.status != "IMPORTED":

        raise FinalImportError(
            f"Batch #{batch.pk} is "
            f"{batch.status}; only imported "
            "batches can be rolled back."
        )

    backup_path = (
        backup_database(
            f"rollback_{batch.pk}"
        )
    )

    reversed_count = 0

    with transaction.atomic():

        locked_batch = (
            ImportBatch.objects
            .select_for_update()
            .get(
                pk=batch.pk
            )
        )

        changes = (
            ImportChange.objects
            .select_for_update()
            .filter(
                import_batch=(
                    locked_batch
                ),
                is_reversed=False,
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        for change in changes:

            instance = None

            if (
                change.object_model
                and change.object_pk
            ):

                try:

                    Model = (
                        apps.get_model(
                            change.object_model
                        )
                    )

                    instance = (
                        Model.objects
                        .filter(
                            pk=(
                                change.object_pk
                            )
                        )
                        .first()
                    )

                except Exception:

                    instance = None

            # Created object: remove it.
            if (
                not change.before_snapshot
                and instance is not None
            ):

                instance.delete()

            # Updated object: restore previous state.
            elif (
                change.before_snapshot
                and instance is not None
            ):

                _restore_snapshot(
                    instance,
                    change.before_snapshot,
                )

            change.is_reversed = True
            change.reversed_at = (
                timezone.now()
            )

            change.save(
                update_fields=[
                    "is_reversed",
                    "reversed_at",
                ]
            )

            reversed_count += 1

        locked_batch.status = (
            "ROLLED_BACK"
        )

        locked_batch.rolled_back_at = (
            timezone.now()
        )

        if user is not None:
            locked_batch.rolled_back_by = (
                user
            )

        update_fields = [
            "status",
            "rolled_back_at",
        ]

        if user is not None:
            update_fields.append(
                "rolled_back_by"
            )

        locked_batch.save(
            update_fields=(
                update_fields
            )
        )

    return {
        "batch_id":
            batch.pk,

        "reversed_changes":
            reversed_count,

        "backup":
            backup_path,

        "status":
            "ROLLED_BACK",
    }
