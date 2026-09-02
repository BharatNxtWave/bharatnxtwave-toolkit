"""
Central Service visibility policy.

Normal BDE users:
    APPROVED / PUBLISHED only

Admins / Super Admins:
    DRAFT / UNDER_REVIEW / APPROVED / PUBLISHED / EXPIRING

ARCHIVED is deliberately excluded.
"""

PUBLIC_SERVICE_STATUSES = (
    "APPROVED",
    "PUBLISHED",
)

ADMIN_PREVIEW_SERVICE_STATUSES = (
    "DRAFT",
    "UNDER_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "EXPIRING",
)


def is_toolkit_admin(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    role = str(
        getattr(user, "role", "")
        or ""
    ).upper()

    return role in {
        "SUPER_ADMIN",
        "ADMIN",
        "IT_ADMIN",
        "DATA_ADMIN",
        "SECURITY_ADMIN",
    }


def visible_service_statuses(user):
    if is_toolkit_admin(user):
        return ADMIN_PREVIEW_SERVICE_STATUSES

    return PUBLIC_SERVICE_STATUSES
