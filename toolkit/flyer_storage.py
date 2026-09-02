from __future__ import annotations

import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import slugify


@deconstructible
class PrivateFlyerStorage(FileSystemStorage):
    """Filesystem storage that deliberately has no public URL."""

    def __init__(self):
        super().__init__(
            location=None,
            base_url=None,
            file_permissions_mode=0o640,
            directory_permissions_mode=0o750,
        )

    @property
    def base_location(self):
        configured = getattr(
            settings,
            "BNW_PRIVATE_UPLOAD_ROOT",
            Path(settings.BASE_DIR) / "private_uploads",
        )
        return str(configured)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError(
            "Private flyer files do not have public URLs. "
            "Use the authenticated preview or download endpoint."
        )


private_flyer_storage = PrivateFlyerStorage()


def service_flyer_upload_to(instance, filename):
    extension = Path(str(filename or "")).suffix.lower()
    service_key = slugify(instance.service.service_id)[:72]

    if not service_key:
        service_key = f"service-{instance.service_id}"

    return (
        f"service_flyers/{service_key}/"
        f"{uuid.uuid4().hex}{extension}"
    )
