from django.urls import path

from . import admin_views, import_views, matcher_views, views

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
        "toolkit/service/<slug:slug>/",
        views.service_detail,
        name="service_detail"
    ),

    path(
        "toolkit/saved/",
        views.saved_services,
        name="saved_services"
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
        "admin-center/import/history/",
        import_views.import_history,
        name="import_history"
    ),

    path(
        "admin-center/import/history/<int:batch_id>/",
        import_views.import_history_detail,
        name="import_history_detail"
    ),
]
