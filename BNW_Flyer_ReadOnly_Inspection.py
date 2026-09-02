"""Read-only contract audit for the BNW Flyer V1 installer.

Run from the Django project root with bytecode writes disabled:

    PYTHONDONTWRITEBYTECODE=1 python manage.py shell < readonly_inspection.py

The database connection is switched to the backend's read-only mode where
available, and every ORM query is additionally protected by a SQL verb guard.
No setting module source or storage credential values are printed.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import os
import re
import shutil
import sys
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.models import Count
from django.template.loader import get_template
from django.urls import URLPattern, URLResolver, get_resolver


EXPECTED_CHECKPOINTS = {
    "toolkit/models.py": (
        "451e117ded0d257f60db78e92aeadb0976be911bb85f6dc727a3816596d325c1"
    ),
    "toolkit/urls.py": (
        "25c3f54e20b5593518f0fd0e3220edc7fcd2c41224d97296aeb94bee8db5e690"
    ),
    "toolkit/views.py": (
        "a3da10aefc7245945dae0baecc53c95105b0d86cd88825947353001efdfd7a65"
    ),
    "toolkit/templates/toolkit/service_detail.html": (
        "0d96bd708e8634e95020335448f4c9e1139b528d72fb324952c2bd1cf08aaf9e"
    ),
    "static/js/bde_workspace.js": (
        "6ff2ee259cc653627a9e3632c80a9c0250bb94707dd7eb094725846d8523e528"
    ),
    "static/css/bde_workspace.css": (
        "f034c6fbe9a1f48c14051045b08193055d980c665486177caecf750095847be8"
    ),
    "templates/base.html": (
        "99a7c714cb1ab4495af38e321b77d43bccb07998804d73a041eb1b707c28ea8c"
    ),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    path = Path(path).resolve()

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def module_path(module_name):
    module = importlib.import_module(module_name)
    source = inspect.getsourcefile(module) or getattr(module, "__file__", "")
    return Path(source).resolve() if source else None


def print_file_checkpoint(path):
    if path is None:
        return

    path = Path(path).resolve()

    if not path.is_file():
        print(relative(path), "| MISSING")
        return

    digest = sha(path)
    expected = EXPECTED_CHECKPOINTS.get(relative(path))
    status = ""

    if expected:
        status = "MATCH" if digest == expected else "MISMATCH"

    print(
        relative(path),
        "| lines:",
        len(path.read_text(encoding="utf-8", errors="replace").splitlines()),
        "| sha256:",
        digest,
        "| checkpoint:",
        status or "recorded",
    )


def print_source(title, source, limit=500):
    lines = str(source or "").splitlines()
    print("\n" + "-" * 96)
    print(title)
    print("-" * 96)

    for number, line in enumerate(lines[:limit], start=1):
        print(f"{number:>5}: {line}")

    if len(lines) > limit:
        print(f"... {len(lines) - limit} additional lines omitted ...")


def print_path_source(path, limit=1800):
    if path is None or not Path(path).is_file():
        return

    path = Path(path).resolve()
    print_source(
        f"FILE SOURCE: {relative(path)} | SHA256: {sha(path)}",
        path.read_text(encoding="utf-8", errors="replace"),
        limit=limit,
    )


def print_function(module, function_name):
    function = getattr(module, function_name, None)

    if function is None:
        print(f"\n{module.__name__}.{function_name}: NOT FOUND")
        return

    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        source = "Source unavailable."

    print_source(
        f"FUNCTION: {module.__name__}.{function_name}",
        source,
        limit=700,
    )


def flatten_patterns(patterns, prefix=""):
    result = []

    for item in patterns:
        if isinstance(item, URLPattern):
            result.append(
                (
                    prefix + str(item.pattern),
                    item.name or "",
                    getattr(item.callback, "__module__", ""),
                    getattr(item.callback, "__name__", ""),
                )
            )
        elif isinstance(item, URLResolver):
            result.extend(
                flatten_patterns(
                    item.url_patterns,
                    prefix + str(item.pattern),
                )
            )

    return result


def read_guard(execute, sql, params, many, context):
    cleaned = re.sub(
        r"^\s*(?:--[^\n]*(?:\n|$)\s*)*",
        "",
        str(sql or ""),
    )
    verb = cleaned.split(None, 1)[0].upper() if cleaned else ""

    if verb not in {
        "SELECT",
        "WITH",
        "PRAGMA",
        "SHOW",
        "DESCRIBE",
        "EXPLAIN",
    }:
        raise RuntimeError(
            f"READ-ONLY INSPECTION BLOCKED SQL: {verb or 'UNKNOWN'}"
        )

    return execute(sql, params, many, context)


root = Path(settings.BASE_DIR).resolve()
settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
settings_path = module_path(settings_module)
root_urls_path = module_path(settings.ROOT_URLCONF)

connection.ensure_connection()
native_read_only = "SQL write blocker active"

try:
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute("PRAGMA query_only = ON")
            native_read_only = "SQLite query_only=ON + SQL write blocker"
        elif connection.vendor == "postgresql":
            cursor.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
            )
            native_read_only = "PostgreSQL read-only + SQL write blocker"
        elif connection.vendor == "mysql":
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            native_read_only = "MySQL read-only + SQL write blocker"
except Exception as exc:
    native_read_only += f" (native mode unavailable: {type(exc).__name__})"


print("\n" + "=" * 96)
print("BNW FLYER FEATURE — COMPLETE READ-ONLY IMPLEMENTATION INSPECTION")
print("=" * 96)
print("Project:", root)
print("Python:", sys.version.replace("\n", " "))
print("Django:", django.get_version())
print("Database vendor:", connection.vendor)
print("Protection:", native_read_only)
print("Settings module:", settings_module)
print("Root URL module:", settings.ROOT_URLCONF)

database_settings = settings.DATABASES.get("default", {})
print("Database engine:", database_settings.get("ENGINE", ""))

if connection.vendor == "sqlite":
    database_path = Path(database_settings.get("NAME", "")).resolve()
    print("SQLite database file:", relative(database_path))
    print("SQLite database exists:", database_path.is_file())
    print(
        "SQLite database size:",
        database_path.stat().st_size if database_path.is_file() else 0,
        "bytes",
    )
    print(
        "SQLite backup parent writable:",
        os.access(database_path.parent, os.W_OK),
    )


with connection.execute_wrapper(read_guard):
    print("\nRUNTIME / SECURITY SETTINGS")

    curated_settings = (
        "DEBUG",
        "MEDIA_ROOT",
        "MEDIA_URL",
        "FILE_UPLOAD_MAX_MEMORY_SIZE",
        "DATA_UPLOAD_MAX_MEMORY_SIZE",
        "FILE_UPLOAD_PERMISSIONS",
        "FILE_UPLOAD_DIRECTORY_PERMISSIONS",
        "X_FRAME_OPTIONS",
        "CSRF_COOKIE_SECURE",
        "SESSION_COOKIE_SECURE",
        "SECURE_CONTENT_TYPE_NOSNIFF",
        "ROOT_URLCONF",
    )

    for name in curated_settings:
        value = getattr(settings, name, "NOT SET")
        print(f"{name}: {value!r}")

    default_storage = getattr(settings, "STORAGES", {}).get("default", {})
    print(
        "DEFAULT STORAGE BACKEND:",
        default_storage.get("BACKEND", "NOT SET"),
    )
    print(
        "DEFAULT STORAGE OPTION NAMES:",
        sorted(default_storage.get("OPTIONS", {}).keys()),
    )

    relevant_middleware = [
        item
        for item in settings.MIDDLEWARE
        if any(
            word in item.lower()
            for word in (
                "csrf",
                "security",
                "auth",
                "clickjacking",
                "csp",
            )
        )
    ]
    print("RELEVANT MIDDLEWARE:")
    for item in relevant_middleware:
        print(" -", item)

    print("\nUPLOAD / PREVIEW DEPENDENCIES")
    for module_name in (
        "PIL",
        "pypdf",
        "fitz",
        "magic",
        "clamd",
    ):
        print(
            module_name,
            "AVAILABLE" if importlib.util.find_spec(module_name) else "NOT INSTALLED",
        )

    print("clamscan executable:", shutil.which("clamscan") or "NOT INSTALLED")
    print("Project directory writable:", os.access(root, os.W_OK))
    print(
        "Free disk space:",
        round(shutil.disk_usage(root).free / (1024 ** 3), 2),
        "GB",
    )

    User = get_user_model()

    print("\nUSER / ADMIN PERMISSION STRUCTURE")
    print("User model:", User._meta.label)

    for field_name in ("role", "is_staff", "is_superuser", "is_active"):
        try:
            field = User._meta.get_field(field_name)
        except Exception:
            print(field_name, "| NOT A DATABASE FIELD")
            continue

        print(
            field_name,
            "| type:",
            field.get_internal_type(),
            "| choices:",
            list(field.choices or []),
        )

    Service = apps.get_model("toolkit", "Service")
    ServiceSource = apps.get_model("toolkit", "ServiceSource")

    print("\nSERVICE / FLYER DATA STRUCTURE")
    print("Total services:", Service.objects.count())
    print(
        "Blank service IDs:",
        Service.objects.filter(service_id="").count(),
    )
    duplicate_ids = list(
        Service.objects
        .values("service_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("service_id", flat=True)
    )
    print("Duplicate service IDs:", duplicate_ids or "NONE")
    print(
        "Service.service_id unique:",
        Service._meta.get_field("service_id").unique,
    )
    print(
        "Existing ServiceSource kinds:",
        list(ServiceSource._meta.get_field("source_kind").choices),
    )

    try:
        apps.get_model("toolkit", "ServiceFlyer")
        print("ServiceFlyer model: ALREADY EXISTS")
    except LookupError:
        print("ServiceFlyer model: NOT PRESENT")

    existing_file_fields = []

    for model in apps.get_models():
        for field in model._meta.get_fields():
            if (
                "flyer" in getattr(field, "name", "").lower()
                or field.__class__.__name__ in {"FileField", "ImageField"}
            ):
                existing_file_fields.append(
                    f"{model._meta.label}.{field.name} "
                    f"({field.__class__.__name__})"
                )

    print(
        "Existing flyer/file fields:",
        existing_file_fields or "NONE",
    )

    print("\nMIGRATION STATE")
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    disk_toolkit = sorted(
        name
        for app_label, name in loader.disk_migrations
        if app_label == "toolkit"
    )
    applied_toolkit = sorted(
        name
        for app_label, name in loader.applied_migrations
        if app_label == "toolkit"
    )
    print("Toolkit migrations on disk:", disk_toolkit)
    print("Toolkit migrations applied:", applied_toolkit)
    print("Toolkit leaf migrations:", loader.graph.leaf_nodes("toolkit"))


print("\nEXACT SOURCE CHECKPOINTS")

checkpoint_paths = [
    root / relative_name
    for relative_name in EXPECTED_CHECKPOINTS
]

additional_paths = [
    root / ".gitignore",
    root / "toolkit/admin_views.py",
    root / "toolkit/import_views.py",
    root / "toolkit/forms.py",
    root / "accounts/models.py",
    root / "accounts/activity.py",
    root / "accounts/decorators.py",
    root / "accounts/permissions.py",
    settings_path,
    root_urls_path,
]

seen_paths = set()

for path in checkpoint_paths + additional_paths:
    if path is None:
        continue

    resolved = Path(path).resolve()

    if resolved in seen_paths:
        continue

    seen_paths.add(resolved)
    print_file_checkpoint(resolved)


print("\nRELEVANT URL CONTRACT")
for route, name, module_name, function_name in flatten_patterns(
    get_resolver().url_patterns
):
    combined = f"{route} {name} {module_name} {function_name}".lower()

    if any(
        fragment in combined
        for fragment in (
            "toolkit",
            "admin-center",
            "import",
            "service",
        )
    ):
        print(
            f"{route} | name={name} | "
            f"view={module_name}.{function_name}"
        )


print_source(
    f"USER MODEL SOURCE: {User.__module__}.{User.__name__}",
    inspect.getsource(User),
    limit=700,
)


activity_module = importlib.import_module("accounts.activity")
print_function(activity_module, "log_activity")


for optional_module_name in (
    "accounts.decorators",
    "accounts.permissions",
):
    try:
        optional_module = importlib.import_module(optional_module_name)
    except ModuleNotFoundError:
        print(f"\n{optional_module_name}: MODULE NOT FOUND")
        continue

    print_path_source(module_path(optional_module_name), limit=1200)


admin_views = importlib.import_module("toolkit.admin_views")
import_views = importlib.import_module("toolkit.import_views")

print_source(
    "toolkit.admin_views imports and permission helpers",
    "\n".join(
        inspect.getsource(admin_views).splitlines()[:220]
    ),
    limit=220,
)

print_source(
    "toolkit.import_views imports and permission helpers",
    "\n".join(
        inspect.getsource(import_views).splitlines()[:260]
    ),
    limit=260,
)

for function_name in (
    "service_management_list",
    "service_create",
    "service_edit",
    "service_verify",
):
    print_function(admin_views, function_name)

for function_name in (
    "import_center",
    "import_extraction_review",
    "import_history",
):
    print_function(import_views, function_name)


print_path_source(root_urls_path, limit=1000)
print_path_source(root / ".gitignore", limit=500)


print("\nADMIN TEMPLATE STRUCTURE")

template_names = {
    "admin_base.html",
}

for module in (admin_views, import_views):
    module_source = inspect.getsource(module)
    template_names.update(
        re.findall(
            r"[\"']([^\"']+\.html)[\"']",
            module_source,
        )
    )

for template_name in sorted(template_names):
    if not any(
        word in template_name.lower()
        for word in (
            "admin",
            "import",
            "service",
            "toolkit",
        )
    ):
        continue

    try:
        template = get_template(template_name)
        origin = getattr(template, "origin", None)
        origin_name = getattr(origin, "name", "")
    except Exception as exc:
        print(
            template_name,
            "| COULD NOT LOAD:",
            type(exc).__name__,
            str(exc),
        )
        continue

    if not origin_name:
        print(template_name, "| LOADED WITHOUT FILE ORIGIN")
        continue

    origin_path = Path(origin_name).resolve()
    print_file_checkpoint(origin_path)

    if template_name == "admin_base.html":
        print_path_source(origin_path, limit=2200)


print("\nFINAL READ-ONLY VERDICT")
print("Database mutation statements allowed by the inspector: 0")
print("Project-file write operations in the inspector: 0")
print("Settings source and storage credential values printed: 0")
print("=" * 96)
