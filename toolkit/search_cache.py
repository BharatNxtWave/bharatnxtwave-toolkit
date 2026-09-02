"""Caching for the deterministic scheme search.

Why this exists
---------------
A single search costs 86 database queries; a four-word search costs 186, and
about three quarters of the request is spent inside it. That is affordable for
a handful of BDEs and is the first thing to fall over at a few hundred
concurrent users.

The work is also highly repetitive. Search results depend only on the query
text and the catalogue - never on who is asking - so when thirty BDEs search
"msme working capital" during the same hour, the catalogue is scanned thirty
times for one answer.

Invalidation
------------
Cached entries are namespaced by a catalogue version. Anything that changes
what a search could return bumps that version, which retires every cached
answer at once - no key tracking, no partial staleness.

`bump_catalog_version()` is wired to post_save/post_delete on the searchable
models (see toolkit/apps.py). Bulk paths that bypass signals - `bulk_create`,
`update`, the workbook import - must call it explicitly.

A TTL is kept as a backstop so a missed bump goes stale within minutes rather
than forever.
"""

from __future__ import annotations

import hashlib

from django.core.cache import cache


VERSION_KEY = "toolkit:catalog-version"

# Backstop only. Correctness comes from the version bump; this bounds the
# damage if some bulk write path forgets to call it.
SEARCH_TTL_SECONDS = 300

# Long: this is retired by version bump, not by expiry.
VERSION_TTL_SECONDS = 24 * 60 * 60


def catalog_version() -> int:
    """Current catalogue generation. Starts at 1 on a cold cache."""

    version = cache.get(VERSION_KEY)

    if version is None:
        version = 1
        cache.set(VERSION_KEY, version, VERSION_TTL_SECONDS)

    return version


def bump_catalog_version(*args, **kwargs) -> None:
    """Retire every cached search answer.

    Accepts and ignores arbitrary arguments so it can be connected directly
    as a signal receiver.
    """

    try:
        cache.incr(VERSION_KEY)

    except ValueError:
        # Key absent or expired - the next read starts a fresh generation,
        # which is itself an invalidation.
        cache.set(VERSION_KEY, 1, VERSION_TTL_SECONDS)


def _key(namespace: str, query: str) -> str:
    digest = hashlib.sha256(
        query.strip().lower().encode("utf-8")
    ).hexdigest()[:32]

    return f"toolkit:{namespace}:v{catalog_version()}:{digest}"


def get_cached_value(namespace: str, query: str):
    """Cached value for `query`, or None when not cached.

    Callers that can legitimately produce None must use a sentinel; the
    search paths here return sets and dicts, where empty is distinguishable
    from absent.
    """

    if not query or not query.strip():
        return None

    return cache.get(_key(namespace, query))


def set_cached_value(namespace: str, query: str, value) -> None:
    if not query or not query.strip():
        return

    cache.set(_key(namespace, query), value, SEARCH_TTL_SECONDS)


def get_cached_ids(namespace: str, query: str):
    """Cached id set for `query`, or None when not cached.

    None means "not cached" and an empty frozenset means "cached, matched
    nothing" - a search that legitimately finds nothing must not be
    recomputed on every request.
    """

    if not query or not query.strip():
        return None

    return cache.get(_key(namespace, query))


def set_cached_ids(namespace: str, query: str, ids) -> None:
    if not query or not query.strip():
        return

    cache.set(
        _key(namespace, query),
        frozenset(ids),
        SEARCH_TTL_SECONDS,
    )
