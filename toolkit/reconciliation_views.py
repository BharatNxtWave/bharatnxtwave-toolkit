from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_http_methods

from toolkit.intelligence.final_import import (
    apply_batch,
    preview_batch,
    rollback_batch,
)
from accounts.portal_access import is_admin_user

from toolkit.models import ImportBatch



def _allowed(user):
    """Delegate to the single definition of "admin" in portal_access.

    This used to accept `is_staff` as well, which portal_access.is_admin_user
    does not. That divergence was only harmless because this view sits under
    the /admin-center/ prefix, where the middleware rejects such a user first;
    moving the route would have turned it into a privilege escalation.
    """

    return is_admin_user(user)


@require_http_methods(["GET", "POST"])
def reconciliation_finalize(
    request,
    batch_id,
):

    if not _allowed(
        request.user
    ):
        return HttpResponseForbidden(
            "Permission denied."
        )

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    metadata = (
        batch.metadata
        if isinstance(
            batch.metadata,
            dict,
        )
        else {}
    )

    if not metadata.get(
        "reconciliation_mode"
    ):

        messages.error(
            request,
            "This is not a reconciliation batch.",
        )

        return redirect(
            "toolkit:import_extraction_review",
            batch_id=batch.pk,
        )

    if request.method == "POST":

        action = str(
            request.POST.get(
                "action",
                "",
            )
        ).strip()

        if action == "final_import":

            try:

                from django.db import (
                    transaction as _one_click_final_transaction,
                )

                with _one_click_final_transaction.atomic():

                    preparation = (
                        _prepare_safe_rows_for_final_import(
                            batch,
                            request.user,
                        )
                    )


                    if preparation["blocking"]:

                        messages.warning(
                            request,
                            (
                                f"{preparation['blocking']} "
                                "item"
                                f"{'s' if preparation['blocking'] != 1 else ''} "
                                "still need your attention. "
                                "Nothing was imported."
                            ),
                        )

                        return redirect(
                            "toolkit:import_extraction_review",
                            batch_id=batch.pk,
                        )


                    if preparation["actionable"] == 0:

                        messages.info(
                            request,
                            (
                                "There are no approved "
                                "Toolkit changes to import."
                            ),
                        )

                        return redirect(
                            "toolkit:import_extraction_review",
                            batch_id=batch.pk,
                        )


                    result = apply_batch(
                        batch.pk,
                        user=request.user,
                        reconcile=True,
                    )

                messages.success(
                    request,
                    (
                        "Final Import completed. "
                        f"{result.get('changes_created', 0)} "
                        "audited change(s) created."
                    ),
                )

            except Exception as exc:

                messages.error(
                    request,
                    f"Final Import failed: {exc}",
                )

        elif action == "rollback":

            try:

                result = rollback_batch(
                    batch.pk,
                    user=request.user,
                )

                messages.success(
                    request,
                    (
                        "Rollback completed. "
                        f"{result.get('reversed_changes', 0)} "
                        "change(s) reversed."
                    ),
                )

            except Exception as exc:

                messages.error(
                    request,
                    f"Rollback failed: {exc}",
                )

        return redirect(
            "toolkit:reconciliation_finalize",
            batch_id=batch.pk,
        )

    batch.refresh_from_db()

    preview = preview_batch(
        batch.pk
    )

    active_changes = (
        batch.changes
        .filter(
            is_reversed=False
        )
        .count()
    )

    return render(
        request,
        "toolkit/admin/reconciliation_finalize.html",
        {
            "batch":
                batch,

            "preview":
                preview,

            "active_changes":
                active_changes,

            "reconciliation_of":
                metadata.get(
                    "reconciliation_of_batch_id"
                ),
        },
    )


# ============================================================
# ONE_CLICK_SAFE_FINAL_IMPORT_V1
# ============================================================

def _prepare_safe_rows_for_final_import(
    batch,
    user,
    dry_run=False,
):
    """
    Prepare an approved reconciliation batch for a
    low-click final import.

    Safety contract:
    - MERGE_REVIEW remains manual.
    - INVALID remains manual/skip.
    - WARNING/PENDING CREATE or UPDATE is blocked.
    - UPDATE requires a matched existing Service.
    - explicitly SKIPPED items stay skipped.
    - already APPROVED items remain approved.
    - safe automatic approvals affect ImportRow review
      metadata only, never live Services.
    """

    from django.db import (
        transaction as _one_click_transaction,
    )

    from django.utils import (
        timezone as _one_click_timezone,
    )


    result = {
        "auto_approved": 0,
        "already_approved": 0,
        "skipped": 0,
        "blocking": 0,
        "blockers": [],
        "actionable": 0,
    }


    if str(
        batch.status
    ).upper() not in {
        "PREVIEWED",
        "VALIDATED",
    }:

        result[
            "blocking"
        ] = 1

        result[
            "blockers"
        ].append(
            (
                "This source is no longer "
                "available for final review."
            )
        )

        return result


    def analyse_rows(rows):

        approvable = []
        blockers = []


        for row in rows:

            action = str(
                row.candidate_action
                or ""
            ).upper()


            raw = (
                dict(row.raw_data)
                if isinstance(
                    row.raw_data,
                    dict,
                )
                else {}
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


            decision = str(
                review.get(
                    "decision",
                    "",
                )
                or ""
            ).upper()


            # --------------------------------------------
            # Knowledge / non-Service rows are not part
            # of this Service approval decision.
            # --------------------------------------------

            if action == "UNDECIDED":

                continue


            # --------------------------------------------
            # Explicitly skipped rows remain skipped.
            # --------------------------------------------

            if (
                action == "SKIP"
                or decision == "SKIPPED"
            ):

                result[
                    "skipped"
                ] += 1

                continue


            # --------------------------------------------
            # Already approved manually.
            # --------------------------------------------

            if (
                action in {
                    "CREATE",
                    "UPDATE",
                }
                and decision == "APPROVED"
            ):

                result[
                    "already_approved"
                ] += 1

                continue


            # --------------------------------------------
            # Ambiguous match MUST remain manual.
            # --------------------------------------------

            if action == "MERGE_REVIEW":

                blockers.append(
                    (
                        row,
                        "Potential duplicate or match "
                        "still needs your decision.",
                    )
                )

                continue


            # --------------------------------------------
            # Invalid rows cannot silently pass.
            # --------------------------------------------

            if action == "INVALID":

                blockers.append(
                    (
                        row,
                        "Invalid incoming item must "
                        "be reviewed or skipped.",
                    )
                )

                continue


            # --------------------------------------------
            # Only CREATE / UPDATE can auto-approve.
            # --------------------------------------------

            if action not in {
                "CREATE",
                "UPDATE",
            }:

                blockers.append(
                    (
                        row,
                        (
                            "Unsupported pending "
                            f"action: {action or 'UNKNOWN'}."
                        ),
                    )
                )

                continue


            # --------------------------------------------
            # Existing pipeline must already consider
            # the row VALID.
            # --------------------------------------------

            if str(
                row.validation_status
            ).upper() != "VALID":

                blockers.append(
                    (
                        row,
                        (
                            "Item is not validated "
                            "as safe yet."
                        ),
                    )
                )

                continue


            # --------------------------------------------
            # UPDATE must point to a real existing
            # Service.
            # --------------------------------------------

            if (
                action == "UPDATE"
                and not row.matched_service_id
            ):

                blockers.append(
                    (
                        row,
                        (
                            "Update has no confirmed "
                            "existing Service match."
                        ),
                    )
                )

                continue


            approvable.append(
                (
                    row,
                    raw,
                    review,
                )
            )


        return (
            approvable,
            blockers,
        )


    # --------------------------------------------------------
    # DRY RUN
    # --------------------------------------------------------

    if dry_run:

        rows = list(
            batch.rows
            .select_related(
                "matched_service"
            )
            .order_by(
                "sheet_name",
                "source_row_number",
            )
        )


        approvable, blockers = (
            analyse_rows(
                rows
            )
        )


        result[
            "auto_approved"
        ] = len(
            approvable
        )


        result[
            "blocking"
        ] = len(
            blockers
        )


        result[
            "blockers"
        ] = [
            {
                "row_id":
                    row.pk,

                "sheet":
                    row.sheet_name,

                "source_row":
                    row.source_row_number,

                "reason":
                    reason,
            }
            for row, reason
            in blockers
        ]


        result[
            "actionable"
        ] = (
            len(
                approvable
            )
            + result[
                "already_approved"
            ]
        )


        return result


    # --------------------------------------------------------
    # REAL PREPARATION
    #
    # Lock candidate rows.
    # Detect blockers FIRST.
    # Write nothing if any blocker exists.
    # --------------------------------------------------------

    with _one_click_transaction.atomic():

        rows = list(
            batch.rows
            .select_for_update()
            .select_related(
                "matched_service"
            )
            .order_by(
                "sheet_name",
                "source_row_number",
            )
        )


        approvable, blockers = (
            analyse_rows(
                rows
            )
        )


        if blockers:

            result[
                "blocking"
            ] = len(
                blockers
            )


            result[
                "blockers"
            ] = [
                {
                    "row_id":
                        row.pk,

                    "sheet":
                        row.sheet_name,

                    "source_row":
                        row.source_row_number,

                    "reason":
                        reason,
                }
                for row, reason
                in blockers
            ]


            result[
                "actionable"
            ] = result[
                "already_approved"
            ]


            # CRITICAL:
            # no automatic approval occurs when
            # unresolved blockers exist.
            return result


        # ----------------------------------------------------
        # No blockers.
        # Safe candidates may now be approved.
        # ----------------------------------------------------

        for (
            row,
            raw,
            review,
        ) in approvable:

            review.update(
                {
                    "decision":
                        "APPROVED",

                    "reviewed_at":
                        _one_click_timezone
                        .now()
                        .isoformat(),

                    "reviewed_by_id":
                        (
                            user.pk
                            if user
                            else None
                        ),

                    "approved_by":
                        (
                            "ONE_CLICK_"
                            "SAFE_FINAL_IMPORT_V1"
                        ),

                    "automatic_safe_approval":
                        True,
                }
            )


            raw[
                "review"
            ] = review


            row.raw_data = raw

            row.validation_status = (
                "VALID"
            )


            row.save(
                update_fields=[
                    "raw_data",
                    "validation_status",
                ]
            )


            result[
                "auto_approved"
            ] += 1


        result[
            "actionable"
        ] = (
            result[
                "auto_approved"
            ]
            + result[
                "already_approved"
            ]
        )


    return result

