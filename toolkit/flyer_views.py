from __future__ import annotations

import hashlib
import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Max, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.activity import log_activity

from .admin_views import can_manage_toolkit
from .flyer_forms import ServiceFlyerUploadForm
from .flyer_validation import inspect_flyer_upload
from .models import Service, ServiceFlyer
from .pitching import VISIBLE_STATUSES


logger = logging.getLogger(__name__)

FLYER_CONFIRMATION_SALT = "toolkit.service-flyer.destination.v1"
FLYER_CONFIRMATION_MAX_AGE = 2 * 60 * 60


def _can_manage_flyers(user):
    from accounts.portal_access import is_admin_user

    return is_admin_user(user)


def flyer_manager_required(view_function):
    @wraps(view_function)
    @login_required
    def guarded(request, *args, **kwargs):
        if not _can_manage_flyers(request.user):
            return HttpResponseForbidden(
                "You do not have permission to manage scheme flyers."
            )

        return view_function(request, *args, **kwargs)

    return guarded


def _user_label(user):
    full_name = ""

    if hasattr(user, "get_full_name"):
        full_name = str(user.get_full_name() or "").strip()

    return full_name or str(getattr(user, "username", "") or user)


def _locked_manager_user(request):
    """Re-read and lock the account before a file or DB row can change."""

    User = get_user_model()

    try:
        user = (
            User._default_manager
            .select_for_update()
            .get(pk=request.user.pk)
        )
    except User.DoesNotExist as exc:
        raise PermissionDenied(
            "Your account is no longer available."
        ) from exc

    if not _can_manage_flyers(user):
        raise PermissionDenied(
            "Your account no longer has flyer-management permission."
        )

    return user


def _destination_token(request, service):
    return signing.dumps(
        {
            "user_pk": request.user.pk,
            "service_pk": service.pk,
            "service_id": service.service_id,
        },
        salt=FLYER_CONFIRMATION_SALT,
        compress=True,
    )


def _destination_is_valid(request, service, token):
    try:
        payload = signing.loads(
            token,
            salt=FLYER_CONFIRMATION_SALT,
            max_age=FLYER_CONFIRMATION_MAX_AGE,
        )
    except signing.BadSignature:
        return False

    return (
        payload.get("user_pk") == request.user.pk
        and payload.get("service_pk") == service.pk
        and payload.get("service_id") == service.service_id
    )


def _current_flyer(service):
    return (
        service.flyers
        .filter(is_current=True)
        .order_by("-version", "-id")
        .first()
    )


@flyer_manager_required
@require_GET
def flyer_manager(request):
    query = str(request.GET.get("q", "") or "").strip()

    current_flyers = ServiceFlyer.objects.filter(
        is_current=True,
    ).order_by("-version", "-id")

    services = (
        Service.objects
        .select_related("domain", "category")
        .prefetch_related(
            Prefetch(
                "flyers",
                queryset=current_flyers,
                to_attr="current_flyer_rows",
            )
        )
        .order_by("title", "service_id")
    )

    if query:
        services = services.filter(
            Q(service_id__icontains=query)
            | Q(title__icontains=query)
        )

    page = Paginator(services, 30).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "toolkit/flyers/flyer_manager.html",
        {
            "page": page,
            "query": query,
            "total_services": Service.objects.count(),
            "services_with_flyers": ServiceFlyer.objects.filter(
                is_current=True,
            ).values("service_id").distinct().count(),
        },
    )


@flyer_manager_required
@require_http_methods(["GET", "POST"])
def flyer_upload(request, service_id):
    service = get_object_or_404(
        Service.objects.select_related("domain", "category"),
        pk=service_id,
    )

    token = _destination_token(request, service)

    if request.method == "POST":
        form = ServiceFlyerUploadForm(request.POST, request.FILES)

        if form.is_valid():
            submitted_token = form.cleaned_data["service_confirmation"]

            if not _destination_is_valid(
                request,
                service,
                submitted_token,
            ):
                form.add_error(
                    None,
                    "The scheme confirmation expired or no longer matches. "
                    "Reload this page before uploading.",
                )
            else:
                uploaded_file = form.cleaned_data["flyer"]
                metadata = form.flyer_metadata
                written_name = ""
                created_flyer = None

                duplicate = (
                    ServiceFlyer.objects
                    .select_related("service")
                    .filter(sha256=metadata["sha256"])
                    .order_by("-is_current", "-version", "-id")
                    .first()
                )

                if duplicate is not None:
                    if duplicate.service_id == service.pk:
                        form.add_error(
                            "flyer",
                            (
                                "This exact file already exists for this "
                                f"scheme as version {duplicate.version}. "
                                "Use version history to restore it."
                            ),
                        )
                    else:
                        form.add_error(
                            "flyer",
                            (
                                "This exact file is already attached to "
                                f"{duplicate.service.title} "
                                f"({duplicate.service.service_id}). "
                                "The upload was stopped for review."
                            ),
                        )

                if not form.errors:
                    try:
                        with transaction.atomic():
                            manager_user = _locked_manager_user(request)
                            locked_service = (
                                Service.objects
                                .select_for_update()
                                .get(pk=service.pk)
                            )

                            if not _destination_is_valid(
                                request,
                                locked_service,
                                submitted_token,
                            ):
                                raise IntegrityError(
                                    "The locked service no longer matches "
                                    "the signed destination."
                                )

                            rechecked_metadata = inspect_flyer_upload(
                                uploaded_file
                            )

                            if rechecked_metadata != metadata:
                                raise IntegrityError(
                                    "The flyer metadata changed between "
                                    "validation and save."
                                )

                            metadata = rechecked_metadata

                            duplicate = (
                                ServiceFlyer.objects
                                .select_for_update()
                                .filter(sha256=metadata["sha256"])
                                .first()
                            )

                            if duplicate is not None:
                                raise IntegrityError(
                                    "The flyer checksum became a duplicate."
                                )

                            latest_version = (
                                ServiceFlyer.objects
                                .filter(service=locked_service)
                                .aggregate(value=Max("version"))["value"]
                                or 0
                            )

                            ServiceFlyer.objects.filter(
                                service=locked_service,
                                is_current=True,
                            ).update(is_current=False)

                            created_flyer = ServiceFlyer(
                                service=locked_service,
                                version=latest_version + 1,
                                original_filename=(
                                    metadata["original_filename"]
                                ),
                                file_kind=metadata["file_kind"],
                                mime_type=metadata["mime_type"],
                                file_size=metadata["file_size"],
                                sha256=metadata["sha256"],
                                service_id_snapshot=(
                                    locked_service.service_id
                                ),
                                service_title_snapshot=(
                                    locked_service.title
                                ),
                                uploaded_by=manager_user,
                                uploaded_by_label=_user_label(manager_user),
                                update_note=form.cleaned_data["update_note"],
                                is_current=True,
                            )

                            created_flyer.file.save(
                                metadata["original_filename"],
                                uploaded_file,
                                save=False,
                            )
                            written_name = created_flyer.file.name
                            created_flyer.save()

                            log_activity(
                                request,
                                "SERVICE_FLYER_UPLOAD",
                                (
                                    "Uploaded scheme flyer: "
                                    f"{locked_service.title} "
                                    f"({locked_service.service_id}), "
                                    f"version {created_flyer.version}."
                                ),
                                target_type="service_flyer",
                                target_id=created_flyer.pk,
                                metadata={
                                    "service_pk": locked_service.pk,
                                    "service_id": locked_service.service_id,
                                    "flyer_version": created_flyer.version,
                                    "sha256": created_flyer.sha256,
                                    "file_size": created_flyer.file_size,
                                },
                            )

                    except PermissionDenied:
                        raise
                    except Exception:
                        if written_name and created_flyer is not None:
                            try:
                                created_flyer.file.storage.delete(
                                    written_name
                                )
                            except Exception:
                                logger.exception(
                                    "Could not remove failed flyer file %s",
                                    written_name,
                                )

                        logger.exception(
                            "Scheme flyer upload failed for service %s",
                            service.pk,
                        )

                        form.add_error(
                            None,
                            (
                                "The flyer was not saved. The existing "
                                "flyer remains unchanged."
                            ),
                        )

                    else:
                        messages.success(
                            request,
                            (
                                f"Flyer version {created_flyer.version} "
                                f"saved to {service.title} "
                                f"({service.service_id})."
                            ),
                        )

                        return redirect(
                            "toolkit:flyer_upload",
                            service_id=service.pk,
                        )

    else:
        form = ServiceFlyerUploadForm(
            initial={
                "service_confirmation": token,
            }
        )

    if request.method == "POST":
        form.fields["service_confirmation"].initial = token

    return render(
        request,
        "toolkit/flyers/flyer_upload.html",
        {
            "service": service,
            "form": form,
            "current_flyer": _current_flyer(service),
            "flyer_history": service.flyers.select_related(
                "uploaded_by",
                "restored_from",
            ).order_by("-version", "-id"),
        },
    )


def _file_response(flyer, download):
    try:
        file_handle = flyer.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("The flyer file is unavailable.")

    response = FileResponse(
        file_handle,
        as_attachment=download,
        filename=flyer.original_filename,
        content_type=flyer.mime_type,
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cross-Origin-Resource-Policy"] = "same-origin"

    return response


@login_required
@require_GET
@xframe_options_sameorigin
def current_flyer_preview(request, service_id):
    flyer = get_object_or_404(
        ServiceFlyer.objects.select_related("service"),
        service_id=service_id,
        is_current=True,
        service__status__in=VISIBLE_STATUSES,
    )
    response = _file_response(flyer, download=False)

    log_activity(
        request,
        "SERVICE_FLYER_PREVIEW",
        f"Previewed scheme flyer: {flyer.service.title}.",
        target_type="service",
        target_id=flyer.service_id,
        metadata={
            "service_id": flyer.service.service_id,
            "flyer_version": flyer.version,
        },
    )

    return response


@login_required
@require_GET
def current_flyer_download(request, service_id):
    flyer = get_object_or_404(
        ServiceFlyer.objects.select_related("service"),
        service_id=service_id,
        is_current=True,
        service__status__in=VISIBLE_STATUSES,
    )
    response = _file_response(flyer, download=True)

    log_activity(
        request,
        "SERVICE_FLYER_DOWNLOAD",
        f"Downloaded scheme flyer: {flyer.service.title}.",
        target_type="service",
        target_id=flyer.service_id,
        metadata={
            "service_id": flyer.service.service_id,
            "flyer_version": flyer.version,
        },
    )

    return response


@flyer_manager_required
@require_GET
@xframe_options_sameorigin
def flyer_version_preview(request, service_id, flyer_id):
    flyer = get_object_or_404(
        ServiceFlyer.objects.select_related("service"),
        pk=flyer_id,
        service_id=service_id,
    )
    return _file_response(flyer, download=False)


@flyer_manager_required
@require_GET
def flyer_version_download(request, service_id, flyer_id):
    flyer = get_object_or_404(
        ServiceFlyer.objects.select_related("service"),
        pk=flyer_id,
        service_id=service_id,
    )
    return _file_response(flyer, download=True)


@flyer_manager_required
@require_POST
def flyer_restore(request, service_id, flyer_id):
    service = get_object_or_404(Service, pk=service_id)
    source = get_object_or_404(
        ServiceFlyer.objects.select_related("service"),
        pk=flyer_id,
        service=service,
    )

    if source.is_current:
        messages.info(
            request,
            f"Version {source.version} is already the current flyer.",
        )
        return redirect(
            "toolkit:flyer_upload",
            service_id=service.pk,
        )

    written_name = ""
    restored = None

    try:
        with transaction.atomic():
            manager_user = _locked_manager_user(request)
            locked_service = (
                Service.objects
                .select_for_update()
                .get(pk=service.pk)
            )
            locked_source = (
                ServiceFlyer.objects
                .select_for_update()
                .get(pk=source.pk, service=locked_service)
            )

            latest_version = (
                ServiceFlyer.objects
                .filter(service=locked_service)
                .aggregate(value=Max("version"))["value"]
                or 0
            )

            ServiceFlyer.objects.filter(
                service=locked_service,
                is_current=True,
            ).update(is_current=False)

            restored = ServiceFlyer(
                service=locked_service,
                version=latest_version + 1,
                original_filename=locked_source.original_filename,
                file_kind=locked_source.file_kind,
                mime_type=locked_source.mime_type,
                file_size=locked_source.file_size,
                sha256=locked_source.sha256,
                service_id_snapshot=locked_service.service_id,
                service_title_snapshot=locked_service.title,
                uploaded_by=manager_user,
                uploaded_by_label=_user_label(manager_user),
                update_note=(
                    f"Restored from flyer version {locked_source.version}."
                ),
                restored_from=locked_source,
                is_current=True,
            )

            try:
                source_handle = locked_source.file.open("rb")
            except (FileNotFoundError, OSError, ValueError):
                raise Http404("The historical flyer file is unavailable.")

            with source_handle:
                digest = hashlib.sha256()
                copied_size = 0

                while True:
                    chunk = source_handle.read(64 * 1024)

                    if not chunk:
                        break

                    copied_size += len(chunk)
                    digest.update(chunk)

                if (
                    copied_size != locked_source.file_size
                    or digest.hexdigest() != locked_source.sha256
                ):
                    raise IntegrityError(
                        "The historical flyer failed its integrity check."
                    )

                source_handle.seek(0)

                restored.file.save(
                    locked_source.original_filename,
                    File(
                        source_handle,
                        name=locked_source.original_filename,
                    ),
                    save=False,
                )

            written_name = restored.file.name
            restored.save()

            log_activity(
                request,
                "SERVICE_FLYER_RESTORE",
                (
                    f"Restored flyer version {locked_source.version} "
                    f"for {locked_service.title} "
                    f"({locked_service.service_id}) as version "
                    f"{restored.version}."
                ),
                target_type="service_flyer",
                target_id=restored.pk,
                metadata={
                    "service_pk": locked_service.pk,
                    "service_id": locked_service.service_id,
                    "restored_from_version": locked_source.version,
                    "new_version": restored.version,
                    "sha256": restored.sha256,
                },
            )

    except (Http404, PermissionDenied):
        raise
    except Exception:
        if written_name and restored is not None:
            try:
                restored.file.storage.delete(written_name)
            except Exception:
                logger.exception(
                    "Could not remove failed restored flyer file %s",
                    written_name,
                )

        logger.exception(
            "Scheme flyer restore failed for service %s",
            service.pk,
        )
        messages.error(
            request,
            "The flyer was not restored. The current version is unchanged.",
        )
    else:
        messages.success(
            request,
            (
                f"Flyer version {source.version} was restored as "
                f"version {restored.version}."
            ),
        )

    return redirect(
        "toolkit:flyer_upload",
        service_id=service.pk,
    )
