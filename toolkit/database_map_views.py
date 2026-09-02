"""
BHARATNXT_VISUAL_DATABASE_MAP_V1

Read-only visual explanation of the Toolkit database.
No database mutation actions exist on this page.
"""

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponseForbidden
from django.shortcuts import render


ADMIN_ROLES = {
    "SUPER_ADMIN",
    "DATA_ADMIN",
    "IT_ADMIN",
    "SECURITY_ADMIN",
}


MODEL_DESCRIPTIONS = {
    "Service":
        "Master record for every scheme, funding program, certification or business service in the Toolkit.",

    "Domain":
        "Top-level business area used to organize Toolkit services.",

    "Category":
        "Groups related Services inside each business domain.",

    "EligibilityRule":
        "Stores individual eligibility conditions linked to a Service.",

    "DocumentRequirement":
        "Documents a client may need for a Service.",

    "ProcessStep":
        "Step-by-step execution or application process.",

    "ServiceContentSection":
        "Structured business information such as benefits, eligibility, scope, funding and notes.",

    "ServiceCommercial":
        "BharatNXT commercial information, fees, deductions and pricing-related details.",

    "ServiceSource":
        "Source or reference information supporting a Service.",

    "KnowledgeSection":
        "Business knowledge connected to Toolkit Services.",

    "ReferenceItem":
        "Reference tables and reusable business information.",

    "CommunicationTemplate":
        "Reusable business communication templates.",

    "ComparisonMatrix":
        "Stores comparison structures between business options or Services.",

    "ComparisonEntry":
        "Individual values inside a comparison matrix.",

    "ImportBatch":
        "One uploaded Excel or CSV source event.",

    "ImportRow":
        "Individual extracted rows staged during an import.",

    "ImportChange":
        "Auditable record of every database change made by an import.",

    "User":
        "Application user and access information.",
}


def _allowed(user):

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return str(
        getattr(
            user,
            "role",
            "",
        )
        or ""
    ).upper() in ADMIN_ROLES


def _group(model):

    name = model.__name__.lower()
    app = model._meta.app_label.lower()


    if any(
        term in name
        for term in (
            "importbatch",
            "importrow",
            "importchange",
        )
    ):
        return "Import & Data Pipeline"


    if any(
        term in name
        for term in (
            "knowledge",
            "reference",
            "communication",
            "comparison",
        )
    ):
        return "Business Knowledge"


    if (
        app in {
            "accounts",
            "auth",
            "admin",
            "sessions",
        }
        or "user" in name
        or "permission" in name
        or "group" == name
    ):
        return "Users & Security"


    if app == "toolkit":
        return "Service Library"


    return "Django System"


def _description(model):

    name = model.__name__

    if name in MODEL_DESCRIPTIONS:
        return MODEL_DESCRIPTIONS[name]

    return (
        f"{name} records used by the "
        f"{model._meta.app_label} application."
    )


def _database_context():

    all_models = sorted(
        apps.get_models(),
        key=lambda model: (
            model._meta.app_label,
            model.__name__,
        ),
    )


    with connection.cursor() as cursor:

        database_tables = set(
            connection.introspection.table_names(
                cursor
            )
        )


    cards = []
    relationships = []
    mapped_tables = set()

    total_fields = 0
    total_records = 0


    for model in all_models:

        table = model._meta.db_table

        mapped_tables.add(table)

        row_count = 0

        if table in database_tables:

            try:

                with connection.cursor() as cursor:

                    cursor.execute(
                        "SELECT COUNT(*) FROM "
                        + connection.ops.quote_name(
                            table
                        )
                    )

                    row_count = (
                        cursor.fetchone()[0]
                    )

            except Exception:
                row_count = 0


        fields = []


        for field in model._meta.get_fields():

            if (
                field.auto_created
                and not field.concrete
            ):
                continue


            field_type = (
                field.get_internal_type()
                if hasattr(
                    field,
                    "get_internal_type",
                )
                else field.__class__.__name__
            )


            related_model = getattr(
                field,
                "related_model",
                None,
            )


            relation = ""

            if related_model is not None:

                relation = (
                    f"{related_model._meta.app_label}."
                    f"{related_model.__name__}"
                )


            fields.append(
                {
                    "name":
                        field.name,

                    "type":
                        field_type,

                    "primary":
                        bool(
                            getattr(
                                field,
                                "primary_key",
                                False,
                            )
                        ),

                    "unique":
                        bool(
                            getattr(
                                field,
                                "unique",
                                False,
                            )
                        ),

                    "nullable":
                        bool(
                            getattr(
                                field,
                                "null",
                                False,
                            )
                        ),

                    "relation":
                        relation,
                }
            )


            if (
                related_model is not None
                and not getattr(
                    field,
                    "auto_created",
                    False,
                )
            ):

                relationships.append(
                    {
                        "source":
                            model.__name__,

                        "field":
                            field.name,

                        "target":
                            related_model.__name__,

                        "type":
                            field_type,
                    }
                )


        total_fields += len(fields)
        total_records += row_count


        cards.append(
            {
                "name":
                    model.__name__,

                "app":
                    model._meta.app_label,

                "table":
                    table,

                "rows":
                    row_count,

                "fields":
                    fields,

                "field_count":
                    len(fields),

                "group":
                    _group(model),

                "description":
                    _description(model),
            }
        )


    group_order = [
        "Service Library",
        "Business Knowledge",
        "Import & Data Pipeline",
        "Users & Security",
        "Django System",
    ]


    group_descriptions = {
        "Service Library":
            "The core business database used by BDEs to search and understand Services.",

        "Business Knowledge":
            "Supporting knowledge, reference material, comparisons and communication content.",

        "Import & Data Pipeline":
            "Tracks source uploads, extracted rows and every audited database change.",

        "Users & Security":
            "Authentication, roles, permissions and user-access information.",

        "Django System":
            "Framework-level tables required to operate the application.",
    }


    groups = []


    for group_name in group_order:

        models = [
            card
            for card in cards
            if card["group"] == group_name
        ]


        if not models:
            continue


        groups.append(
            {
                "name":
                    group_name,

                "description":
                    group_descriptions[
                        group_name
                    ],

                "models":
                    models,

                "records":
                    sum(
                        item["rows"]
                        for item in models
                    ),
            }
        )


    card_lookup = {
        card["name"]: card
        for card in cards
    }


    unmapped = []


    for table in sorted(
        database_tables
        - mapped_tables
    ):

        count = 0

        try:

            with connection.cursor() as cursor:

                cursor.execute(
                    "SELECT COUNT(*) FROM "
                    + connection.ops.quote_name(
                        table
                    )
                )

                count = (
                    cursor.fetchone()[0]
                )

        except Exception:
            pass


        unmapped.append(
            {
                "table":
                    table,

                "rows":
                    count,
            }
        )


    service_children = [
        relation
        for relation in relationships
        if relation["target"] == "Service"
    ]


    service_outgoing = [
        relation
        for relation in relationships
        if relation["source"] == "Service"
    ]


    return {
        "groups":
            groups,

        "cards":
            cards,

        "relationships":
            relationships,

        "service_children":
            service_children,

        "service_outgoing":
            service_outgoing,

        "unmapped_tables":
            unmapped,

        "stats": {
            "models":
                len(cards),

            "relationships":
                len(relationships),

            "fields":
                total_fields,

            "records":
                total_records,

            "services":
                card_lookup.get(
                    "Service",
                    {},
                ).get(
                    "rows",
                    0,
                ),

            "import_rows":
                card_lookup.get(
                    "ImportRow",
                    {},
                ).get(
                    "rows",
                    0,
                ),

            "import_batches":
                card_lookup.get(
                    "ImportBatch",
                    {},
                ).get(
                    "rows",
                    0,
                ),
        },
    }


@login_required
def database_map(request):

    if not _allowed(
        request.user
    ):

        return HttpResponseForbidden(
            "You do not have permission "
            "to view the Database Map."
        )


    return render(
        request,
        "toolkit/admin/database_map.html",
        _database_context(),
    )
