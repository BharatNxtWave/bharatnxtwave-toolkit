from django import template


register = template.Library()


@register.simple_tag
def current_service_flyer(service):
    if service is None or not getattr(service, "pk", None):
        return None

    return (
        service.flyers
        .filter(is_current=True)
        .order_by("-version", "-id")
        .first()
    )
