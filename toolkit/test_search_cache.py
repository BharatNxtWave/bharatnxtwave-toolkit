"""Correctness tests for the cached search paths.

The cache exists for speed, but a cache that returns a different answer than
the code it fronts is worse than a slow search - a BDE would be shown the
wrong schemes on a client call and have no way to tell.

These tests assert the cached wrappers agree with the uncached functions, and
that a catalogue change is actually reflected rather than served stale.
"""

from django.core.cache import cache
from django.test import TestCase
from django.utils.text import slugify

from toolkit import views
from toolkit.models import Category, Service, ServiceDomain
from toolkit.search_cache import bump_catalog_version, catalog_version


class SearchCacheCorrectnessTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.domain = ServiceDomain.objects.create(
            name="Cache Domain",
            slug="cache-domain",
            description="Automated test domain.",
        )

        cls.category = Category.objects.create(
            domain=cls.domain,
            name="Cache Category",
            slug="cache-category",
            description="Automated test category.",
        )

        kind = Service.SERVICE_KIND_CHOICES[0][0]

        titles = [
            "HDFC Working Capital Credit Scheme",
            "ICICI MSME Term Loan Programme",
            "Axis Export Invoice Discounting",
            "SBI Supply Chain Finance Facility",
        ]

        for i, title in enumerate(titles):
            Service.objects.create(
                service_id=f"CACHE-{i:04d}",
                title=title,
                slug=slugify(title),
                domain=cls.domain,
                category=cls.category,
                service_kind=kind,
            )

    def setUp(self):
        cache.clear()

    QUERIES = [
        "credit",
        "working capital",
        "msme term loan",
        "export invoice discounting",
        "zzz nothing matches this zzz",
    ]

    # -- agreement with the uncached implementation --------------------------

    def test_cached_match_ids_agree_with_uncached(self):
        for query in self.QUERIES:
            with self.subTest(query=query):
                cache.clear()

                expected = views.natural_language_match_ids(
                    views.all_bde_services(),
                    query,
                )

                cold = views.cached_catalog_match_ids(query)
                warm = views.cached_catalog_match_ids(query)

                self.assertEqual(set(cold), set(expected))
                self.assertEqual(set(warm), set(expected))

    def test_cached_rank_map_agrees_with_uncached(self):
        for query in self.QUERIES:
            with self.subTest(query=query):
                cache.clear()

                expected = views.natural_language_rank_map(
                    views.all_bde_services(),
                    query,
                )

                cold = views.cached_catalog_rank_map(query)
                warm = views.cached_catalog_rank_map(query)

                self.assertEqual(cold, expected)
                self.assertEqual(warm, expected)

    def test_empty_result_is_cached_not_recomputed(self):
        """A search that matches nothing must still be cached.

        Treating "no matches" as "not cached" would make the most expensive
        searches - the ones scanning everything and finding nothing - the
        only ones never served from cache.
        """

        query = "zzz nothing matches this zzz"

        first = views.cached_catalog_match_ids(query)
        self.assertEqual(set(first), set())

        from toolkit.search_cache import get_cached_ids

        self.assertIsNotNone(
            get_cached_ids("nlmatch", query),
            "An empty match set was not stored in the cache.",
        )

    # -- invalidation --------------------------------------------------------

    def test_new_service_is_visible_to_search_immediately(self):
        """The regression that matters: stale results after a catalogue edit."""

        query = "hyperspecific quantum widget"

        self.assertEqual(set(views.cached_catalog_match_ids(query)), set())

        title = "Kotak Hyperspecific Quantum Widget Facility"

        Service.objects.create(
            service_id="CACHE-NEW-1",
            title=title,
            slug=slugify(title),
            domain=self.domain,
            category=self.category,
            service_kind=Service.SERVICE_KIND_CHOICES[0][0],
        )

        matched = views.cached_catalog_match_ids(query)

        expected = views.natural_language_match_ids(
            views.all_bde_services(),
            query,
        )

        self.assertEqual(set(matched), set(expected))

    def test_saving_a_service_bumps_the_catalog_version(self):
        before = catalog_version()

        service = Service.objects.first()
        service.title = service.title + " Updated"
        service.save()

        self.assertGreater(catalog_version(), before)

    def test_deleting_a_service_bumps_the_catalog_version(self):
        before = catalog_version()

        Service.objects.first().delete()

        self.assertGreater(catalog_version(), before)

    def test_bump_retires_previously_cached_answers(self):
        query = "working capital"

        views.cached_catalog_match_ids(query)

        from toolkit.search_cache import get_cached_ids

        self.assertIsNotNone(get_cached_ids("nlmatch", query))

        bump_catalog_version()

        self.assertIsNone(
            get_cached_ids("nlmatch", query),
            "A version bump did not retire the cached answer.",
        )
