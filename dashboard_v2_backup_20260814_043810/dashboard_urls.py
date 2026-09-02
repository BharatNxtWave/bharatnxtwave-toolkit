from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path(
        "",
        views.home,
        name="home"
    ),

    path(
        "admin-center/",
        views.admin_overview,
        name="admin_overview"
    ),

    path(
        "admin-center/bde-analytics/",
        views.bde_analytics,
        name="bde_analytics"
    ),

    path(
        "search-activity/",
        views.search_activity_detail,
        name="search_activity_detail",
    ),
]
