from .models import ActivityLog
from .network_security import get_request_ip


def log_activity(
    request,
    action,
    description,
    target_type="",
    target_id="",
    metadata=None,
):
    user = None

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
    ):
        user = request.user

    ActivityLog.objects.create(
        user=user,
        action=action,
        description=description,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        ip_address=get_request_ip(request) or None,
        user_agent=request.META.get(
            "HTTP_USER_AGENT",
            ""
        ),
        metadata=metadata or {},
    )
