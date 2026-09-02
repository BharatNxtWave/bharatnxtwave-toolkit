from django.urls import path

from . import admin_views, import_views, matcher_views, reconciliation_views, views, database_map_views, flyer_views

app_name = "toolkit"

urlpatterns = [
    path(
        "toolkit/",
        views.toolkit_home,
        name="home"
    ),
    path(
        "toolkit/search/suggestions/",
        views.search_suggestions,
        name="search_suggestions"
    ),
    path(
        "toolkit/library/",
        views.service_library,
        name="service_library"
    ),
    path(
        "toolkit/library/quick/<int:service_id>/",
        views.service_quick_view,
        name="service_quick_view"
    ),
    path(
        "toolkit/recent/",
        views.recent_services,
        name="recent_services"
    ),
    path(
        "toolkit/service/<slug:slug>/",
        views.service_detail,
        name="service_detail"
    ),

    # BNW_EXTERNAL_LINK_TRACKING_V1
    path(
        "toolkit/service/<int:service_id>/source/<int:source_id>/open/",
        views.service_source_open,
        name="service_source_open",
    ),

    path(
        "toolkit/saved/",
        views.saved_services,
        name="saved_services"
    ),

    # BNX_SAVED_COLLECTIONS_V1
    path(
        "toolkit/saved/collection/create/",
        views.saved_collection_create,
        name="saved_collection_create",
    ),
    path(
        "toolkit/saved/collection/<int:collection_id>/",
        views.saved_collection_detail,
        name="saved_collection_detail",
    ),
    path(
        "toolkit/saved/collection/<int:collection_id>/rename/",
        views.saved_collection_rename,
        name="saved_collection_rename",
    ),
    path(
        "toolkit/saved/collection/<int:collection_id>/delete/",
        views.saved_collection_delete,
        name="saved_collection_delete",
    ),
    path(
        "toolkit/saved/collection/<int:collection_id>/item/<int:item_id>/remove/",
        views.saved_collection_remove_item,
        name="saved_collection_remove_item",
    ),
    path(
        "toolkit/service/<int:service_id>/collections/",
        views.saved_service_collection_state,
        name="saved_service_collection_state",
    ),
    path(
        "toolkit/service/<int:service_id>/collections/action/",
        views.saved_service_collection_action,
        name="saved_service_collection_action",
    ),

    path(
        "toolkit/matcher/",
        matcher_views.client_matcher,
        name="client_matcher"
    ),
    path(
        "toolkit/service/<int:service_id>/save/",
        views.toggle_saved_service,
        name="toggle_saved_service"
    ),

    # BNW_FLYER_ROUTES_V1
    path(
        "toolkit/service/<int:service_id>/flyer/preview/",
        flyer_views.current_flyer_preview,
        name="current_flyer_preview",
    ),
    path(
        "toolkit/service/<int:service_id>/flyer/download/",
        flyer_views.current_flyer_download,
        name="current_flyer_download",
    ),
    path(
        "admin-center/toolkit/flyers/",
        flyer_views.flyer_manager,
        name="flyer_manager",
    ),
    path(
        "admin-center/toolkit/flyers/<int:service_id>/",
        flyer_views.flyer_upload,
        name="flyer_upload",
    ),
    path(
        "admin-center/toolkit/flyers/<int:service_id>/version/<int:flyer_id>/preview/",
        flyer_views.flyer_version_preview,
        name="flyer_version_preview",
    ),
    path(
        "admin-center/toolkit/flyers/<int:service_id>/version/<int:flyer_id>/download/",
        flyer_views.flyer_version_download,
        name="flyer_version_download",
    ),
    path(
        "admin-center/toolkit/flyers/<int:service_id>/version/<int:flyer_id>/restore/",
        flyer_views.flyer_restore,
        name="flyer_restore",
    ),

    path(
        "admin-center/toolkit/",
        admin_views.service_management_list,
        name="admin_service_list"
    ),
    path(
        "admin-center/toolkit/pitch-windows/",
        admin_views.pitch_window_list,
        name="pitch_windows"
    ),
    path(
        "admin-center/toolkit/add/",
        admin_views.service_create,
        name="admin_service_create"
    ),
    path(
        "admin-center/toolkit/<int:service_id>/edit/",
        admin_views.service_edit,
        name="admin_service_edit"
    ),
    path(
        "admin-center/toolkit/<int:service_id>/verify/",
        admin_views.service_verify,
        name="admin_service_verify"
    ),

    path(
        "admin-center/import/",
        import_views.import_center,
        name="import_center"
    ),
    path(
        "admin-center/import/<int:batch_id>/review/",
        import_views.import_extraction_review,
        name="import_extraction_review",
    ),

    path(
        "admin-center/import/<int:batch_id>/review/<int:row_id>/decision/",
        import_views.import_extraction_row_decision,
        name="import_extraction_row_decision",
    ),

    # ADMIN_IMPORT_UX_V2
    path(
        "admin-center/import/<int:batch_id>/review/approve-safe/",
        import_views.import_bulk_safe_approve,
        name="import_bulk_safe_approve"
    ),

    # BNW_STANDARD_IMPORT_FINALIZE_V1
    path(
        "admin-center/import/<int:batch_id>/apply/",
        import_views.import_finalize,
        name="import_finalize",
    ),

    path(
        "admin-center/import/<int:batch_id>/finalize/",
        reconciliation_views.reconciliation_finalize,
        name="reconciliation_finalize"
    ),
    path(
        "admin-center/import/history/",
        import_views.import_history,
        name="import_history"
    ),
    path(
        "admin-center/import/history/<int:batch_id>/",
        import_views.import_history_detail,
        name="import_history_detail"
    ),
    path(
        "admin-center/import/history/<int:batch_id>/delete/",
        import_views.import_source_delete,
        name="import_source_delete",
    ),
    path(
        "admin-center/database-map/",
        database_map_views.database_map,
        name="database_map"
    ),
]
