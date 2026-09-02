from django.contrib import admin

from .models import (
    ServiceDomain,
    Category,
    Service,
    EligibilityRule,
    DocumentRequirement,
    ProcessStep,
    ServiceSource,
    RelatedService,
)


@admin.register(ServiceDomain)
class ServiceDomainAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "display_order", "is_active")
    search_fields = ("name",)
    list_filter = ("domain", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "service_id",
        "title",
        "domain",
        "category",
        "service_kind",
        "status",
        "last_verified_at",
    )

    search_fields = (
        "service_id",
        "title",
        "bde_summary",
    )

    list_filter = (
        "status",
        "service_kind",
        "domain",
        "category",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }


admin.site.register(EligibilityRule)
admin.site.register(DocumentRequirement)
admin.site.register(ProcessStep)
admin.site.register(ServiceSource)
admin.site.register(RelatedService)
