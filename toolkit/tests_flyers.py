from __future__ import annotations

import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, Service, ServiceDomain, ServiceFlyer


PDF_ONE = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PDF_TWO = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog>>\nendobj\n%%EOF\n"


class ServiceFlyerWorkflowTests(TestCase):

    def setUp(self):
        self.private_root = tempfile.mkdtemp(
            prefix="bnw_flyer_test_"
        )
        self.settings_override = override_settings(
            BNW_PRIVATE_UPLOAD_ROOT=self.private_root
        )
        self.settings_override.enable()

        User = get_user_model()

        self.admin = User.objects.create_user(
            username="flyer-admin",
            password="test-password",
        )
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

        self.bde = User.objects.create_user(
            username="flyer-bde",
            password="test-password",
        )

        try:
            role_field = User._meta.get_field("role")
        except Exception:
            role_field = None

        if role_field is not None:
            choices = {
                value
                for value, _label in role_field.choices
            }

            if "SUPER_ADMIN" in choices:
                self.admin.role = "SUPER_ADMIN"
                self.admin.save(update_fields=["role"])

            if "BDE" in choices:
                self.bde.role = "BDE"
                self.bde.save(update_fields=["role"])

        self.domain = ServiceDomain.objects.create(
            name="Flyer Test Domain",
            slug="flyer-test-domain",
        )
        self.category = Category.objects.create(
            domain=self.domain,
            name="Flyer Test Category",
            slug="flyer-test-category",
        )
        self.service = Service.objects.create(
            service_id="BNXT-SVC-FLYERTEST01",
            title="Flyer Test Scheme",
            slug="flyer-test-scheme",
            domain=self.domain,
            category=self.category,
            service_kind="GOVT_SCHEME",
            status="PUBLISHED",
            benefits="Verified test benefit",
            eligibility_summary="Verified test eligibility",
            industries=["Test sector"],
        )
        self.second_service = Service.objects.create(
            service_id="BNXT-SVC-FLYERTEST02",
            title="Second Flyer Test Scheme",
            slug="second-flyer-test-scheme",
            domain=self.domain,
            category=self.category,
            service_kind="GOVT_SCHEME",
            status="PUBLISHED",
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.private_root, ignore_errors=True)

    def _token(self, service=None):
        service = service or self.service
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse(
                "toolkit:flyer_upload",
                args=[service.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        return response.context["form"]["service_confirmation"].value()

    def _upload(self, content, name="official-flyer.pdf", service=None):
        service = service or self.service
        token = self._token(service)

        with patch("toolkit.flyer_views.log_activity"):
            return self.client.post(
                reverse(
                    "toolkit:flyer_upload",
                    args=[service.pk],
                ),
                {
                    "service_confirmation": token,
                    "update_note": "Approved test upload",
                    "flyer": SimpleUploadedFile(
                        name,
                        content,
                        content_type="application/pdf",
                    ),
                },
                follow=False,
            )

    def test_bde_cannot_open_flyer_manager(self):
        self.client.force_login(self.bde)
        response = self.client.get(reverse("toolkit:flyer_manager"))
        self.assertEqual(response.status_code, 403)

    def test_opening_upload_page_does_not_create_a_flyer(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse(
                "toolkit:flyer_upload",
                args=[self.service.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceFlyer.objects.exists())

    def test_signed_destination_cannot_be_reused_for_another_service(self):
        token = self._token(self.service)

        with patch("toolkit.flyer_views.log_activity"):
            response = self.client.post(
                reverse(
                    "toolkit:flyer_upload",
                    args=[self.second_service.pk],
                ),
                {
                    "service_confirmation": token,
                    "flyer": SimpleUploadedFile(
                        "wrong-destination.pdf",
                        PDF_ONE,
                        content_type="application/pdf",
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceFlyer.objects.exists())
        self.assertContains(response, "no longer matches")

    def test_permission_is_rechecked_immediately_before_save(self):
        token = self._token(self.service)
        self.admin.is_staff = False
        self.admin.is_superuser = False

        try:
            role_field = self.admin._meta.get_field("role")
        except Exception:
            role_field = None

        if role_field is not None:
            choices = {
                value
                for value, _label in role_field.choices
            }

            if "BDE" in choices:
                self.admin.role = "BDE"

        self.admin.save()

        with patch("toolkit.flyer_views.log_activity"):
            response = self.client.post(
                reverse(
                    "toolkit:flyer_upload",
                    args=[self.service.pk],
                ),
                {
                    "service_confirmation": token,
                    "flyer": SimpleUploadedFile(
                        "permission-recheck.pdf",
                        PDF_ONE,
                        content_type="application/pdf",
                    ),
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ServiceFlyer.objects.exists())

    def test_upload_is_bound_to_exact_service_and_preserves_scheme(self):
        original = {
            "service_id": self.service.service_id,
            "title": self.service.title,
            "benefits": self.service.benefits,
            "eligibility_summary": self.service.eligibility_summary,
            "industries": self.service.industries,
        }

        response = self._upload(PDF_ONE)
        self.assertEqual(response.status_code, 302)

        flyer = ServiceFlyer.objects.get(service=self.service)
        self.assertEqual(flyer.version, 1)
        self.assertTrue(flyer.is_current)
        self.assertEqual(flyer.service_id_snapshot, original["service_id"])
        self.assertEqual(flyer.service_title_snapshot, original["title"])
        self.assertEqual(flyer.mime_type, "application/pdf")
        self.assertTrue(flyer.file.storage.exists(flyer.file.name))

        self.service.refresh_from_db()

        for field_name, expected in original.items():
            self.assertEqual(
                getattr(self.service, field_name),
                expected,
            )

    def test_update_creates_history_and_one_current_version(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)
        self.assertEqual(
            self._upload(PDF_TWO, "official-flyer-v2.pdf").status_code,
            302,
        )

        versions = list(
            ServiceFlyer.objects
            .filter(service=self.service)
            .order_by("version")
        )
        self.assertEqual([item.version for item in versions], [1, 2])
        self.assertFalse(versions[0].is_current)
        self.assertTrue(versions[1].is_current)
        self.assertEqual(
            ServiceFlyer.objects.filter(
                service=self.service,
                is_current=True,
            ).count(),
            1,
        )

    def test_duplicate_file_for_another_service_is_blocked(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)

        response = self._upload(
            PDF_ONE,
            service=self.second_service,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ServiceFlyer.objects.filter(
                service=self.second_service
            ).exists()
        )
        self.assertContains(
            response,
            "already attached to Flyer Test Scheme",
        )

    def test_false_pdf_is_rejected_without_changing_current_flyer(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)
        current_pk = ServiceFlyer.objects.get(
            service=self.service,
            is_current=True,
        ).pk

        response = self._upload(
            b"This is not really a PDF.",
            "fake.pdf",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "file contents do not match",
        )
        self.assertEqual(
            ServiceFlyer.objects.get(
                service=self.service,
                is_current=True,
            ).pk,
            current_pk,
        )

    def test_bde_can_preview_and_download_only_current_flyer(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)
        self.client.force_login(self.bde)

        preview = self.client.get(
            reverse(
                "toolkit:current_flyer_preview",
                args=[self.service.pk],
            )
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "application/pdf")
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("inline", preview["Content-Disposition"])
        self.assertEqual(b"".join(preview.streaming_content), PDF_ONE)

        download = self.client.get(
            reverse(
                "toolkit:current_flyer_download",
                args=[self.service.pk],
            )
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(b"".join(download.streaming_content), PDF_ONE)

    def test_restore_copies_old_file_into_new_audit_version(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)
        first = ServiceFlyer.objects.get(
            service=self.service,
            version=1,
        )
        self.assertEqual(
            self._upload(PDF_TWO, "official-flyer-v2.pdf").status_code,
            302,
        )

        self.client.force_login(self.admin)

        with patch("toolkit.flyer_views.log_activity"):
            response = self.client.post(
                reverse(
                    "toolkit:flyer_restore",
                    args=[self.service.pk, first.pk],
                )
            )

        self.assertEqual(response.status_code, 302)
        restored = ServiceFlyer.objects.get(
            service=self.service,
            is_current=True,
        )
        self.assertEqual(restored.version, 3)
        self.assertEqual(restored.restored_from_id, first.pk)
        self.assertEqual(restored.sha256, first.sha256)
        self.assertNotEqual(restored.file.name, first.file.name)
        self.assertTrue(restored.file.storage.exists(restored.file.name))

    def test_restore_refuses_a_tampered_historical_file(self):
        self.assertEqual(self._upload(PDF_ONE).status_code, 302)
        first = ServiceFlyer.objects.get(
            service=self.service,
            version=1,
        )
        self.assertEqual(
            self._upload(PDF_TWO, "official-flyer-v2.pdf").status_code,
            302,
        )
        current = ServiceFlyer.objects.get(
            service=self.service,
            is_current=True,
        )

        with first.file.storage.open(first.file.name, "wb") as handle:
            handle.write(b"tampered historical file")

        self.client.force_login(self.admin)

        with patch("toolkit.flyer_views.log_activity"):
            response = self.client.post(
                reverse(
                    "toolkit:flyer_restore",
                    args=[self.service.pk, first.pk],
                )
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ServiceFlyer.objects.get(
                service=self.service,
                is_current=True,
            ).pk,
            current.pk,
        )
        self.assertEqual(
            ServiceFlyer.objects.filter(service=self.service).count(),
            2,
        )
