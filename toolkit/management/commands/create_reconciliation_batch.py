import hashlib
from collections import Counter
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from toolkit.intelligence.delta import (
    classify_candidate,
)
from toolkit.intelligence.final_import import (
    backup_database,
)
from toolkit.intelligence.ingestion import (
    analyse_file,
)
from toolkit.intelligence.staging import (
    stage_analysis,
)
from toolkit.models import (
    ImportBatch,
    ImportRow,
)


SOURCE = Path(
    "confidential_source/"
    "BHARATNXT  WAVE_POWER _ TOOLKIT.xlsx"
)


class Command(BaseCommand):

    help = (
        "Create a fresh reconciliation batch "
        "using the latest ingestion and delta engines."
    )


    def handle(
        self,
        *args,
        **options,
    ):

        if not SOURCE.exists():

            raise CommandError(
                f"Source workbook not found: {SOURCE}"
            )


        # ====================================================
        # SOURCE HASH
        # ====================================================

        source_bytes = (
            SOURCE.read_bytes()
        )

        digest = hashlib.sha256(
            source_bytes
        ).hexdigest()


        original = (
            ImportBatch.objects
            .filter(
                file_sha256=digest,
                status="IMPORTED",
            )
            .order_by(
                "id"
            )
            .first()
        )


        if original is None:

            raise CommandError(
                "No imported source with the same "
                "SHA exists. Reconciliation is not appropriate."
            )


        self.stdout.write(
            f"Imported source: #{original.pk}"
        )

        self.stdout.write(
            f"SHA: {digest}"
        )


        # ====================================================
        # LATEST ANALYSIS — READ SOURCE
        # ====================================================

        with SOURCE.open(
            "rb"
        ) as handle:

            analysis = analyse_file(
                handle,
                SOURCE.name,
            )


        candidate_count = sum(
            len(
                sheet.get(
                    "candidates",
                    [],
                )
            )
            for sheet
            in analysis.get(
                "sheets",
                []
            )
        )


        self.stdout.write(
            f"Latest candidates: {candidate_count}"
        )


        if candidate_count != 186:

            raise CommandError(
                "Safety stop: latest engine did not "
                f"produce expected clean candidate set. "
                f"Got {candidate_count}, expected 186."
            )


        # ====================================================
        # BACKUP BEFORE STAGING WRITE
        # ====================================================

        backup = backup_database(
            "reconciliation"
        )


        self.stdout.write(
            f"Database backup: {backup}"
        )


        # ====================================================
        # CREATE + STAGE ATOMICALLY
        # ====================================================

        try:

            with transaction.atomic():

                batch = ImportBatch.objects.create(
                    source_type="XLSX",

                    source_name=(
                        "RECONCILIATION — "
                        + SOURCE.name
                    )[:255],

                    source_identifier=str(
                        SOURCE
                    ),

                    file_sha256=digest,

                    sheet_count=len(
                        analysis.get(
                            "sheets",
                            []
                        )
                    ),

                    status="PREVIEWED",

                    metadata={
                        "reconciliation_mode":
                            True,

                        "reconciliation_of_batch_id":
                            original.pk,

                        # Important:
                        # review UI must not treat this
                        # controlled reconciliation batch
                        # as the redundant duplicate screen.
                        "duplicate_detected":
                            False,

                        "exact_source_duplicate":
                            True,

                        "latest_engine_candidate_count":
                            candidate_count,
                    },
                )


                with SOURCE.open(
                    "rb"
                ) as handle:

                    stage_result = stage_analysis(
                        batch,
                        analysis,
                        handle,
                        SOURCE.name,
                    )


                # --------------------------------------------
                # CURRENT DELTA CLASSIFICATION
                # --------------------------------------------

                counts = Counter()

                unsafe = []

                safe_additions = []


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


                for row in rows:

                    raw = (
                        dict(
                            row.raw_data
                        )
                        if isinstance(
                            row.raw_data,
                            dict,
                        )
                        else {}
                    )


                    candidate = raw.get(
                        "candidate",
                        {}
                    )


                    if not isinstance(
                        candidate,
                        dict,
                    ) or not candidate:

                        continue


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


                    # Persist the delta result so the
                    # review UI can use it directly.
                    raw[
                        "delta"
                    ] = {
                        "status":
                            status,

                        "matched_service_id":
                            delta.get(
                                "matched_service_id"
                            ),

                        "matched_service_title":
                            delta.get(
                                "matched_service_title"
                            ),

                        "differences":
                            delta.get(
                                "differences",
                                [],
                            ),
                    }


                    if status == "NO_CHANGE":

                        # Hide unchanged rows from the
                        # Needs Attention workflow.
                        row.candidate_action = (
                            "SKIP"
                        )


                        review = (
                            dict(
                                raw.get(
                                    "review",
                                    {},
                                )
                            )
                            if isinstance(
                                raw.get(
                                    "review",
                                    {},
                                ),
                                dict,
                            )
                            else {}
                        )


                        review.update(
                            {
                                "decision":
                                    "SKIPPED",

                                "reason":
                                    "NO_CHANGE",

                                "automatic":
                                    True,
                            }
                        )


                        raw[
                            "review"
                        ] = review


                    elif status == "SAFE_ADDITION":

                        # Existing Service receives
                        # additional business knowledge.
                        row.candidate_action = (
                            "UPDATE"
                        )


                        review = (
                            dict(
                                raw.get(
                                    "review",
                                    {},
                                )
                            )
                            if isinstance(
                                raw.get(
                                    "review",
                                    {},
                                ),
                                dict,
                            )
                            else {}
                        )


                        review.update(
                            {
                                "decision":
                                    "PENDING",

                                "reason":
                                    "SAFE_ADDITION",

                                "automatic":
                                    False,
                            }
                        )


                        raw[
                            "review"
                        ] = review


                        safe_additions.append(
                            {
                                "row_id":
                                    row.pk,

                                "sheet":
                                    row.sheet_name,

                                "source_row":
                                    row.source_row_number,

                                "title":
                                    candidate.get(
                                        "title"
                                    ),

                                "service_id":
                                    delta.get(
                                        "matched_service_id"
                                    ),

                                "service_title":
                                    delta.get(
                                        "matched_service_title"
                                    ),

                                "differences":
                                    delta.get(
                                        "differences",
                                        [],
                                    ),
                            }
                        )


                    else:

                        unsafe.append(
                            {
                                "row_id":
                                    row.pk,

                                "title":
                                    candidate.get(
                                        "title"
                                    ),

                                "status":
                                    status,
                            }
                        )


                    row.raw_data = raw


                    row.save(
                        update_fields=[
                            "raw_data",
                            "candidate_action",
                        ]
                    )


                # --------------------------------------------
                # HARD SAFETY
                # --------------------------------------------

                if unsafe:

                    raise RuntimeError(
                        "Unsafe delta found in reconciliation: "
                        + str(
                            unsafe
                        )
                    )


                if counts[
                    "NO_CHANGE"
                ] != 184:

                    raise RuntimeError(
                        "Expected 184 NO_CHANGE candidates; "
                        f"got {counts['NO_CHANGE']}."
                    )


                if counts[
                    "SAFE_ADDITION"
                ] != 2:

                    raise RuntimeError(
                        "Expected 2 SAFE_ADDITION candidates; "
                        f"got {counts['SAFE_ADDITION']}."
                    )


                batch.row_count = (
                    batch.rows.count()
                )


                metadata = dict(
                    batch.metadata
                    or {}
                )


                metadata[
                    "reconciliation_delta"
                ] = {
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
                }


                metadata[
                    "safe_addition_row_ids"
                ] = [
                    item[
                        "row_id"
                    ]
                    for item
                    in safe_additions
                ]


                batch.metadata = metadata


                batch.save(
                    update_fields=[
                        "row_count",
                        "metadata",
                    ]
                )


        except Exception as exc:

            raise CommandError(
                f"Reconciliation creation rolled back: {exc}"
            )


        # ====================================================
        # RESULT
        # ====================================================

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "RECONCILIATION BATCH CREATED"
            )
        )

        self.stdout.write(
            f"Batch: #{batch.pk}"
        )

        self.stdout.write(
            f"Physical source rows: "
            f"{batch.row_count}"
        )

        self.stdout.write(
            f"Candidates: "
            f"{sum(counts.values())}"
        )

        self.stdout.write(
            f"Delta counts: "
            f"{dict(counts)}"
        )


        self.stdout.write(
            "\n===== NEEDS REVIEW ====="
        )


        for item in safe_additions:

            self.stdout.write("")

            self.stdout.write(
                f"ImportRow #{item['row_id']}"
            )

            self.stdout.write(
                f"{item['sheet']} "
                f"row {item['source_row']}"
            )

            self.stdout.write(
                f"{item['title']} "
                f"→ {item['service_title']}"
            )


            for difference in (
                item[
                    "differences"
                ]
            ):

                value = str(
                    difference.get(
                        "incoming",
                        "",
                    )
                )


                if len(value) > 180:

                    value = (
                        value[:177]
                        + "..."
                    )


                self.stdout.write(
                    "  + "
                    + str(
                        difference.get(
                            "field"
                        )
                    )
                    + " | "
                    + value
                )


        self.stdout.write("")
        self.stdout.write(
            "BUSINESS DATA CHANGES: 0"
        )

        self.stdout.write(
            "Only reconciliation staging "
            "records were created."
        )
