import hashlib
import json
from pathlib import Path

from django.db import transaction

from toolkit.models import (
    ImportRow,
    Service,
)

from .ingestion import (
    csv_sheets,
    xlsx_sheets,
)


def make_hash(payload):

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def source_sheets(
    file_obj,
    filename,
):

    extension = Path(
        filename
    ).suffix.lower()

    if extension == ".xlsx":

        return xlsx_sheets(
            file_obj
        )

    if extension == ".csv":

        return csv_sheets(
            file_obj
        )

    raise ValueError(
        "Only .xlsx and .csv are supported."
    )


def stage_analysis(
    batch,
    analysis,
    file_obj,
    filename,
):

    # --------------------------------------------------------
    # IDEMPOTENCY
    # --------------------------------------------------------

    if batch.rows.exists():

        return {
            "staged": False,
            "reason": "already_staged",
            "source_rows": batch.rows.count(),
            "candidate_rows": (
                batch.rows
                .exclude(
                    candidate_action="UNDECIDED"
                )
                .count()
            ),
        }

    # --------------------------------------------------------
    # MAP INTELLIGENCE CANDIDATES TO PHYSICAL SOURCE ROWS
    # --------------------------------------------------------

    candidate_map = {}

    sheet_kind = {}

    for sheet in analysis.get(
        "sheets",
        [],
    ):

        name = sheet.get(
            "name",
            "",
        )

        sheet_kind[name] = sheet.get(
            "kind",
            "UNKNOWN",
        )

        for candidate in sheet.get(
            "candidates",
            [],
        ):

            row_number = int(
                candidate.get(
                    "source_row",
                    0,
                )
                or 0
            )

            if row_number <= 0:
                continue

            key = (
                name,
                row_number,
            )

            # One source row should not silently represent
            # multiple Service candidates.
            if key in candidate_map:

                raise ValueError(
                    "Multiple Service candidates detected "
                    f"for {name} row {row_number}."
                )

            candidate_map[key] = (
                candidate
            )

    # --------------------------------------------------------
    # READ EVERY NON-EMPTY PHYSICAL SOURCE ROW
    # --------------------------------------------------------

    physical_sheets = source_sheets(
        file_obj,
        filename,
    )

    objects = []

    source_row_count = 0
    candidate_count = 0

    action_counts = {
        "CREATE": 0,
        "UPDATE": 0,
        "MERGE_REVIEW": 0,
        "SKIP": 0,
        "INVALID": 0,
        "UNDECIDED": 0,
    }

    for (
        sheet_name,
        rows,
    ) in physical_sheets:

        family = sheet_kind.get(
            sheet_name,
            "UNKNOWN",
        )

        for (
            row_number,
            values,
            links,
        ) in rows:

            source_row_count += 1

            candidate = candidate_map.get(
                (
                    sheet_name,
                    row_number,
                )
            )

            action = "UNDECIDED"

            matched_service_id = None

            validation_status = "VALID"

            warnings = []

            errors = []

            source_key = ""

            if candidate:

                candidate_count += 1

                source_key = str(
                    candidate.get(
                        "title",
                        "",
                    )
                ).strip()[:255]

                match = (
                    candidate.get(
                        "match",
                        {}
                    )
                    or {}
                )

                action = match.get(
                    "action",
                    "UNDECIDED",
                )

                if action not in action_counts:

                    action = "UNDECIDED"

                matched_service_id = (
                    match.get(
                        "matched_service_id"
                    )
                )

                if (
                    matched_service_id
                    and not Service.objects.filter(
                        pk=matched_service_id
                    ).exists()
                ):

                    warnings.append(
                        "Suggested matched Service "
                        "does not exist anymore."
                    )

                    matched_service_id = None

                    action = "MERGE_REVIEW"

                if action == "MERGE_REVIEW":

                    validation_status = (
                        "WARNING"
                    )

                    warnings.append(
                        "Human review required "
                        "before import."
                    )

                elif action == "INVALID":

                    validation_status = (
                        "INVALID"
                    )

                    errors.append(
                        "Candidate could not be "
                        "safely interpreted."
                    )

            if not source_key:

                for value in values:

                    cleaned = str(
                        value or ""
                    ).strip()

                    if cleaned:

                        source_key = (
                            cleaned[:255]
                        )

                        break

            payload = {
                "engine_version":
                    analysis.get(
                        "engine_version",
                        "unknown",
                    ),

                "sheet_kind":
                    family,

                "business_knowledge_visibility":
                    "BDE",

                "source": {
                    "row_number":
                        row_number,

                    "values":
                        values,

                    "links":
                        links,
                },

                "candidate":
                    candidate,
            }

            action_counts[action] += 1

            objects.append(
                ImportRow(
                    import_batch=batch,

                    sheet_name=(
                        sheet_name
                    ),

                    source_row_number=(
                        row_number
                    ),

                    source_key=(
                        source_key
                    ),

                    row_hash=make_hash(
                        payload
                    ),

                    raw_data=payload,

                    validation_status=(
                        validation_status
                    ),

                    validation_errors=(
                        errors
                    ),

                    validation_warnings=(
                        warnings
                    ),

                    candidate_action=(
                        action
                    ),

                    matched_service_id=(
                        matched_service_id
                    ),
                )
            )

    # --------------------------------------------------------
    # ONE TRANSACTION
    # --------------------------------------------------------

    with transaction.atomic():

        ImportRow.objects.bulk_create(
            objects,
            batch_size=500,
        )

        metadata = dict(
            batch.metadata or {}
        )

        metadata[
            "intelligence_staging"
        ] = {
            "engine_version":
                analysis.get(
                    "engine_version"
                ),

            "all_business_knowledge_retained":
                True,

            "business_knowledge_visibility":
                "BDE",

            "source_rows":
                source_row_count,

            "candidate_rows":
                candidate_count,

            "non_candidate_business_rows":
                (
                    source_row_count
                    - candidate_count
                ),

            "candidate_actions":
                action_counts,
        }

        batch.metadata = metadata

        batch.save(
            update_fields=[
                "metadata",
            ]
        )

    return {
        "staged": True,

        "source_rows":
            source_row_count,

        "candidate_rows":
            candidate_count,

        "non_candidate_business_rows":
            (
                source_row_count
                - candidate_count
            ),

        "actions":
            action_counts,
    }
