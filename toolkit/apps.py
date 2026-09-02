from django.apps import AppConfig


class ToolkitConfig(AppConfig):
    name = 'toolkit'

    def ready(self):
        """Retire cached search answers whenever the catalogue changes.

        Search results are cached under a catalogue version (see
        toolkit/search_cache.py). Every model the search actually reads has
        to bump that version, or a BDE keeps seeing a stale answer for up to
        the cache TTL.

        Signals do not fire for bulk_create/update/raw SQL, so the workbook
        import calls bump_catalog_version() explicitly as well.
        """

        from django.db.models.signals import post_delete, post_save

        from .search_cache import bump_catalog_version

        # The tables the search queries, plus the classification models that
        # decide which services are visible in the first place.
        searchable = (
            "Service",
            "ServiceContentSection",
            "ServiceCommercial",
            "ServiceSource",
            "KnowledgeSection",
            "EligibilityRule",
            "ServiceClassification",
            "DocumentRequirement",
            "ProcessStep",
            "Category",
        )

        for name in searchable:
            model = self.get_model(name)

            post_save.connect(
                bump_catalog_version,
                sender=model,
                dispatch_uid=f"bnw-search-cache-save-{name}",
            )

            post_delete.connect(
                bump_catalog_version,
                sender=model,
                dispatch_uid=f"bnw-search-cache-delete-{name}",
            )
