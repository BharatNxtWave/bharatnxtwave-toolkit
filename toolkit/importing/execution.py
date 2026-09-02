"""Atomic BharatNXT Wave controlled import and rollback engine."""

from __future__ import annotations

from copy import deepcopy

from django.apps import apps
from django.db import connection, transaction
from django.utils import timezone

from toolkit.importing.final_plan import build_final_import_plan
from toolkit.importing.transformation import load_verified_context
from toolkit.models import (
    Category,
    CommunicationTemplate,
    ComparisonEntry,
    ComparisonMatrix,
    ImportBatch,
    ImportChange,
    ImportRow,
    KnowledgeDocument,
    KnowledgeSection,
    ReferenceItem,
    Service,
    ServiceClassification,
    ServiceCommercial,
    ServiceDomain,
    ServiceSource,
)

EXPECTED_BASELINE = {
    "Service": 1,
    "Category": 32,
    "ImportRow": 478,
    "ImportChange": 0,
    "ServiceClassification": 0,
    "ServiceCommercial": 0,
    "ServiceSource": 0,
    "ServiceContentSection": 0,
    "ReferenceItem": 0,
    "ComparisonMatrix": 0,
    "ComparisonEntry": 0,
    "CommunicationTemplate": 0,
    "KnowledgeDocument": 0,
    "KnowledgeSection": 0,
}


def _count(name):
    return apps.get_model("toolkit", name).objects.count()


def baseline_counts():
    return {name: _count(name) for name in EXPECTED_BASELINE}


def assert_preimport_baseline():
    actual = baseline_counts()
    if actual != EXPECTED_BASELINE:
        raise RuntimeError(
            f"Pre-import database baseline changed. Expected={EXPECTED_BASELINE}; Actual={actual}"
        )
    return actual


def database_integrity():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()
        cursor.execute("PRAGMA foreign_key_check;")
        fk_rows = cursor.fetchall()
    result = integrity[0] if integrity else "NO RESULT"
    if result != "ok" or fk_rows:
        raise RuntimeError(
            f"SQLite integrity failed: integrity={result}, foreign_keys={len(fk_rows)}"
        )
    return {"integrity_check": result, "foreign_key_violations": 0}


def _record_change(*, batch, action, obj, import_row=None, service=None):
    return ImportChange.objects.create(
        import_batch=batch,
        import_row=import_row,
        service=service,
        action=action,
        object_model=obj._meta.label,
        object_pk=str(obj.pk),
        before_snapshot={},
        after_snapshot={"model": obj._meta.label, "pk": str(obj.pk)},
    )


def _resolve_categories(plan, batch):
    domains = {obj.slug: obj for obj in ServiceDomain.objects.all()}
    category_map = {
        (obj.domain.slug, obj.slug): obj
        for obj in Category.objects.select_related("domain").all()
    }
    created = []
    for item in plan["core"]["categories"]:
        pair = (item["domain_slug"], item["slug"])
        if pair in category_map:
            raise RuntimeError(f"Planned Category unexpectedly already exists: {pair}")
        domain = domains.get(item["domain_slug"])
        if domain is None:
            raise RuntimeError("Planned Category references a missing domain.")
        obj = Category.objects.create(
            domain=domain,
            name=item["name"],
            slug=item["slug"],
            description=item.get("description", ""),
            display_order=item.get("display_order", 0),
            is_active=True,
        )
        category_map[pair] = obj
        created.append(obj)
        _record_change(batch=batch, action="OTHER", obj=obj)
    return category_map, created


def _service_kwargs(item, category_map):
    pair = (item["domain_slug"], item["category_slug"])
    category = category_map.get(pair)
    if category is None:
        raise RuntimeError(f"Service primary category unavailable: {pair}")
    return {
        "service_id": item["service_id"],
        "title": item["title"],
        "slug": item["slug"],
        "domain": category.domain,
        "category": category,
        "service_kind": item["service_kind"],
        "status": "DRAFT",
        "priority": item.get("priority", "NORMAL"),
        "benefits": item.get("benefits", ""),
        "eligibility_summary": item.get("eligibility_summary", ""),
        "funding_organisation": item.get("funding_organisation", ""),
        "applicable_for_raw": item.get("applicable_for_raw", ""),
        "application_deadline_raw": item.get("application_deadline_raw", ""),
        "application_deadline": item.get("application_deadline"),
        "deadline_status": item.get("deadline_status", "UNKNOWN"),
        "important_notes": item.get("important_notes", ""),
    }


def _execute(plan):
    contract_v3, batch, staged_rows = load_verified_context()
    if batch.pk != plan["batch_id"] or batch.status != "PREVIEWED":
        raise RuntimeError(
            f"Batch #{batch.pk} must be PREVIEWED before import; current={batch.status}"
        )
    if ImportChange.objects.filter(import_batch=batch).exists():
        raise RuntimeError("Batch already has ImportChange rows.")

    batch.status = "IMPORTING"
    batch.save(update_fields=["status"])

    category_map, created_categories = _resolve_categories(plan, batch)
    service_map = {}

    for identity, item in plan["core"]["services"].items():
        obj = Service.objects.create(**_service_kwargs(item, category_map))
        service_map[identity] = obj
        _record_change(
            batch=batch,
            action="SERVICE_CREATE",
            obj=obj,
            service=obj,
        )

    rows_by_id = {row.id: row for row in staged_rows}

    for item in plan["core"]["classifications"]:
        service = service_map[item["service_identity"]]
        pair = (item["domain_slug"], item["category_slug"])
        category = category_map.get(pair)
        if category is None:
            raise RuntimeError(f"Classification category unavailable: {pair}")
        obj = ServiceClassification.objects.create(
            service=service,
            category=category,
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="CLASSIFICATION_ADD",
            obj=obj,
            import_row=obj.source_import_row,
            service=service,
        )

    for item in plan["core"]["commercial"]:
        service = service_map[item["service_identity"]]
        obj = ServiceCommercial.objects.create(
            service=service,
            label=item["label"],
            minimum_charge_raw=item["minimum_charge_raw"],
            minimum_charge=item["minimum_charge"],
            government_fee_raw=item["government_fee_raw"],
            government_fee=item["government_fee"],
            vendor_cost_raw=item["vendor_cost_raw"],
            vendor_cost=item["vendor_cost"],
            bdm_deduction_raw=item["bdm_deduction_raw"],
            bdm_deduction=item["bdm_deduction"],
            remarks=item["remarks"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
            is_active=item.get("is_active", True),
        )
        _record_change(
            batch=batch,
            action="COMMERCIAL_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
            service=service,
        )

    for item in plan["sources"]["plans"]:
        service = service_map[item["service_identity"]]
        obj = ServiceSource.objects.create(
            service=service,
            source_name=item["source_name"],
            source_url=item["source_url"],
            source_kind=item["source_kind"],
            import_row=rows_by_id.get(item.get("import_row_id")),
            source_reference=item["source_reference"],
            is_official=item["is_official"],
            notes=item["notes"],
        )
        _record_change(
            batch=batch,
            action="SOURCE_ADD",
            obj=obj,
            import_row=obj.import_row,
            service=service,
        )

    for item in plan["references"]:
        obj = ReferenceItem.objects.create(
            dataset_name=item["dataset_name"],
            key=item["key"],
            value=item["value"],
            metadata=item["metadata"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="REFERENCE_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
        )

    matrix_plan = plan["comparison"]["matrix"]
    matrix = ComparisonMatrix.objects.create(
        name=matrix_plan["name"],
        source_sheet=matrix_plan["source_sheet"],
        import_batch=batch,
        metadata=matrix_plan["metadata"],
    )
    _record_change(batch=batch, action="OTHER", obj=matrix)

    for item in plan["comparison"]["entries"]:
        linked_service = (
            service_map.get(item.get("service_identity"))
            if item.get("service_identity")
            else None
        )
        obj = ComparisonEntry.objects.create(
            matrix=matrix,
            row_number=item["row_number"],
            column_name=item["column_name"],
            row_label=item["row_label"],
            value_raw=item["value_raw"],
            service=linked_service,
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="OTHER",
            obj=obj,
            import_row=obj.source_import_row,
            service=linked_service,
        )

    document_map = {}
    for item in plan["knowledge"]["documents"]:
        obj = KnowledgeDocument.objects.create(
            document_key=item["document_key"],
            title=item["title"],
            source_sheet=item["source_sheet"],
            source_import_batch=batch,
            status="DRAFT",
            visibility="ADMIN_ONLY",
            metadata=item["metadata"],
        )
        document_map[item["document_key"]] = obj
        _record_change(batch=batch, action="OTHER", obj=obj)

    for item in plan["knowledge"]["sections"]:
        linked_service = (
            service_map.get(item["linked_service_identity"])
            if item.get("linked_service_identity")
            else None
        )
        obj = KnowledgeSection.objects.create(
            document=document_map[item["document_key"]],
            linked_service=linked_service,
            section_type=item["section_type"],
            title=item["title"],
            content=item["content"],
            display_order=item["display_order"],
            is_heading=item["is_heading"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id[item["source_import_row_id"]],
        )
        _record_change(
            batch=batch,
            action="CONTENT_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
            service=linked_service,
        )

    comm = plan["communication"]
    template = CommunicationTemplate.objects.create(
        template_key=comm["template_key"],
        title=comm["title"],
        subject=comm["subject"],
        body=comm["body"],
        status="DRAFT",
        visibility="ADMIN_ONLY",
        source_import_batch=batch,
        source_sheet=comm["source_sheet"],
    )
    _record_change(batch=batch, action="OTHER", obj=template)

    service_for_row = {}
    merge_row_ids = set()
    for identity, item in plan["core"]["services"].items():
        service = service_map[identity]
        for row_id in item["source_row_ids"]:
            service_for_row[row_id] = service
        merge_row_ids.update(item.get("rolling_merge_row_ids", []))

    now = timezone.now()
    for row in staged_rows:
        row.import_outcomes = plan["row_outcomes"][row.id]
        row.processed_at = now
        row.imported_service = service_for_row.get(row.id)
        row.matched_service = service_for_row.get(row.id) if row.id in merge_row_ids else None
        row.save(
            update_fields=[
                "import_outcomes",
                "processed_at",
                "imported_service",
                "matched_service",
            ]
        )

    batch.status = "IMPORTED"
    batch.imported_at = now
    metadata = deepcopy(batch.metadata or {})
    metadata["final_import"] = {
        "contract_version": 4,
        "services": len(service_map),
        "categories_created": len(created_categories),
        "knowledge_documents": len(document_map),
        "knowledge_sections": len(plan["knowledge"]["sections"]),
        "row_outcomes": len(plan["row_outcomes"]),
        "rolling_lineage": plan["rolling_lineage_audit"],
        "business_field_audit": plan["business_field_audit"],
        "preserve_only_by_sheet": plan["preserve_only_by_sheet"],
    }
    batch.metadata = metadata
    batch.save(update_fields=["status", "imported_at", "metadata"])

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "services_created": len(service_map),
        "categories_created": len(created_categories),
        "knowledge_documents": len(document_map),
        "knowledge_sections": len(plan["knowledge"]["sections"]),
        "row_outcomes": len(plan["row_outcomes"]),
        "ledger_rows": ImportChange.objects.filter(import_batch=batch).count(),
    }


def preflight():
    baseline = assert_preimport_baseline()
    integrity = database_integrity()
    plan = build_final_import_plan()
    if plan["rolling_lineage_audit"] != {"covered": 7, "merged": 5, "new": 2}:
        raise RuntimeError("Rolling lineage preflight failed.")
    if len(plan["row_outcomes"]) != 478:
        raise RuntimeError("478-row reconciliation failed.")
    return {
        "database": integrity,
        "baseline": baseline,
        "plan": {
            "services": len(plan["core"]["services"]),
            "categories": len(plan["core"]["categories"]),
            "classifications": len(plan["core"]["classifications"]),
            "commercial": len(plan["core"]["commercial"]),
            "sources": len(plan["sources"]["plans"]),
            "references": len(plan["references"]),
            "comparison_entries": len(plan["comparison"]["entries"]),
            "knowledge_documents": len(plan["knowledge"]["documents"]),
            "knowledge_sections": len(plan["knowledge"]["sections"]),
            "communication_templates": 1,
            "row_outcomes": len(plan["row_outcomes"]),
            "rolling_lineage": plan["rolling_lineage_audit"],
            "business_field_audit": plan["business_field_audit"],
            "preserve_only_by_sheet": plan["preserve_only_by_sheet"],
        },
    }


def rehearse_import():
    before = baseline_counts()
    assert_preimport_baseline()
    plan = build_final_import_plan()
    with transaction.atomic():
        _execute(plan)
        transaction.set_rollback(True)
    after = baseline_counts()
    if after != before:
        raise RuntimeError(f"Forced rollback changed counts. Before={before}; After={after}")
    batch = ImportBatch.objects.get(pk=5)
    if batch.status != "PREVIEWED":
        raise RuntimeError("Forced rollback changed Batch #5 status.")
    dirty_rows = ImportRow.objects.filter(import_batch=batch, processed_at__isnull=False).count()
    if dirty_rows:
        raise RuntimeError("Forced rollback left processed ImportRows.")
    return {
        "rehearsal": "PASS",
        "counts_unchanged": True,
        "batch_status": batch.status,
        "processed_rows_after_rollback": dirty_rows,
    }


def run_import():
    assert_preimport_baseline()
    database_integrity()
    plan = build_final_import_plan()
    with transaction.atomic():
        result = _execute(plan)
    database_integrity()
    return result


def rollback_import(rolled_back_by=None):
    batch = ImportBatch.objects.get(pk=5)
    if batch.status != "IMPORTED":
        raise RuntimeError(f"Batch #5 must be IMPORTED; current={batch.status}")
    changes = list(
        ImportChange.objects.filter(import_batch=batch, is_reversed=False).order_by("-id")
    )
    if not changes:
        raise RuntimeError("No unreversed ImportChange ledger rows exist.")
    now = timezone.now()
    with transaction.atomic():
        for change in changes:
            if change.object_model and change.object_pk:
                try:
                    app_label, model_name = change.object_model.split(".", 1)
                    model = apps.get_model(app_label, model_name)
                except Exception as exc:
                    raise RuntimeError(
                        f"Rollback cannot resolve model {change.object_model!r}."
                    ) from exc
                obj = model.objects.filter(pk=change.object_pk).first()
                if obj is not None:
                    obj.delete()
            change.is_reversed = True
            change.reversed_at = now
            change.save(update_fields=["is_reversed", "reversed_at"])

        for row in ImportRow.objects.filter(import_batch=batch):
            row.imported_service = None
            row.matched_service = None
            row.processed_at = None
            row.import_outcomes = []
            row.save(
                update_fields=[
                    "imported_service",
                    "matched_service",
                    "processed_at",
                    "import_outcomes",
                ]
            )

        batch.status = "ROLLED_BACK"
        batch.rolled_back_at = now
        batch.rolled_back_by = rolled_back_by
        batch.save(update_fields=["status", "rolled_back_at", "rolled_back_by"])
    database_integrity()
    return {
        "rollback": "PASS",
        "batch_status": batch.status,
        "ledger_rows_reversed": len(changes),
    }
