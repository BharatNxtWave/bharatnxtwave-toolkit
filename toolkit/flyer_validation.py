from __future__ import annotations

import hashlib
import re
from pathlib import Path

from django.core.exceptions import ValidationError


MAX_FLYER_BYTES = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf": ("PDF", "application/pdf"),
    ".png": ("IMAGE", "image/png"),
    ".jpg": ("IMAGE", "image/jpeg"),
    ".jpeg": ("IMAGE", "image/jpeg"),
}


def clean_original_filename(value):
    filename = Path(str(value or "")).name
    filename = re.sub(r"[\x00-\x1f\x7f]+", "", filename).strip()

    if not filename:
        filename = "scheme-flyer"

    extension = Path(filename).suffix.lower()
    stem = Path(filename).stem[:220].rstrip(" .") or "scheme-flyer"

    return f"{stem}{extension}"


def _signature_matches(extension, header):
    if extension == ".pdf":
        return header.find(b"%PDF-") in range(0, min(len(header), 1024))

    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")

    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")

    return False


def inspect_flyer_upload(uploaded_file):
    filename = clean_original_filename(uploaded_file.name)
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Upload a PDF, JPG, JPEG or PNG flyer."
        )

    declared_size = int(getattr(uploaded_file, "size", 0) or 0)

    if declared_size <= 0:
        raise ValidationError("The selected flyer is empty.")

    if declared_size > MAX_FLYER_BYTES:
        raise ValidationError(
            "The flyer is larger than the 20 MB limit."
        )

    uploaded_file.seek(0)
    header = uploaded_file.read(1024)

    if not _signature_matches(extension, header):
        raise ValidationError(
            "The file contents do not match its PDF or image extension."
        )

    uploaded_file.seek(0)
    digest = hashlib.sha256()
    actual_size = 0

    for chunk in uploaded_file.chunks():
        actual_size += len(chunk)

        if actual_size > MAX_FLYER_BYTES:
            uploaded_file.seek(0)
            raise ValidationError(
                "The flyer is larger than the 20 MB limit."
            )

        digest.update(chunk)

    uploaded_file.seek(0)

    if actual_size <= 0:
        raise ValidationError("The selected flyer is empty.")

    if actual_size != declared_size:
        raise ValidationError(
            "The uploaded file size changed during validation. Try again."
        )

    file_kind, mime_type = ALLOWED_EXTENSIONS[extension]

    return {
        "original_filename": filename,
        "extension": extension,
        "file_kind": file_kind,
        "mime_type": mime_type,
        "file_size": actual_size,
        "sha256": digest.hexdigest(),
    }
