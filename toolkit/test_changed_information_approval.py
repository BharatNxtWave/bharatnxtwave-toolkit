"""Behavioural tests for the CHANGED_INFORMATION approval guard.

`test_changed_information_review_ui.py` asserts that the guard's *source text*
exists. That is not enough: the guard shipped with a NameError
(`messages` / `redirect` were never imported in `toolkit/import_views.py`,
which uses the aliased `_review_messages` / `_review_redirect` instead), so the
guard raised instead of blocking cleanly, and a source-text assertion still
passed.

These tests execute the view, so a regression of that kind fails loudly.
"""

from hashlib import sha256
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from toolkit.models import (
    Category,
    ImportBatch,
    ImportRow,
    Service,
    ServiceDomain,
)


User = get_user_model()


class ChangedInformationApprovalTests(TestCase):
    """The approval guard must redirect with a message, never raise."""

    @classmethod
    def setUpTestData(cls):
        cls.domain = ServiceDomain.objects.create(
            name="Approval Guard Domain",
            slug="approval-guard-domain",
            description="Automated test classification.",
        )

        cls.category = Category.objects.create(
            domain=cls.domain,
            name="Approval Guard Category",
            slug="approval-guard-category",
            description="Automated test classification.",
        )

        cls.service_kind = Service.SERVICE_KIND_CHOICES[0][0]

        cls.password = "guard-test-password-4821"

        cls.admin = User.objects.create_user(
            username="approval_guard_admin",
            password=cls.password,
            role="DATA_ADMIN",
        )

    def setUp(self):
        self.client.force_login(self.admin)

        self.batch = ImportBatch.objects.create(
            source_type="XLSX",
            source_name="approval-guard.xlsx",
            source_identifier="approval-guard-source",
            file_sha256="",
            sheet_count=1,
            row_count=1,
            status="PREVIEWED",
            metadata={},
        )

        self.row = self._make_row(self.batch)

    def _make_row(self, batch, row_number=2):
        title = "Approval Guard Scheme"

        source_data = {
            "row_number": row_number,
            "values": {"Scheme Name": title},
            "links": [],
        }

        raw_data = {
            "engine_version": "automated-test-v1",
            "sheet_kind": "SCHEME",
            "business_knowledge_visibility": "ADMIN_ONLY",
            "source": source_data,
            "candidate": {
                "title": title,
                "fields": {},
                "links": [],
                "match": {},
                "proposal": {},
                "source_row": source_data,
                "extraction_mode": "AUTOMATED_TEST",
            },
            "review": {
                "automatic": False,
                "decision": "PENDING",
                "reason": "Automated approval guard test.",
                "reviewed_at": None,
                "reviewed_by_id": None,
                "category_id": self.category.pk,
                "service_kind": self.service_kind,
            },
        }

        fingerprint = sha256(
            f"{batch.pk}:{row_number}:{title}".encode("utf-8")
        ).hexdigest()

        return ImportRow.objects.create(
            import_batch=batch,
            sheet_name="Schemes",
            source_row_number=row_number,
            source_key=f"approval-guard-{batch.pk}-{row_number}",
            row_hash=fingerprint,
            raw_data=raw_data,
            validation_status="VALID",
            candidate_action="CREATE",
        )

    def _decision_url(self):
        return reverse(
            "toolkit:import_extraction_row_decision",
            kwargs={
                "batch_id": self.batch.pk,
                "row_id": self.row.pk,
            },
        )

    def _approve(self, delta_status):
        """POST an approval while the classifier reports `delta_status`."""

        target = "toolkit.intelligence.final_import.classify_candidate"

        with patch(target, return_value={"status": delta_status}):
            return self.client.post(
                self._decision_url(),
                {"decision": "approve"},
            )

    def test_replacement_approval_redirects_instead_of_raising(self):
        """The guard blocks CHANGED_INFORMATION without a 500.

        This is the regression test for the NameError: before the fix this
        call raised `NameError: name 'messages' is not defined` instead of
        returning a redirect.
        """

        response = self._approve("CHANGED_INFORMATION")

        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            response["Location"],
            reverse(
                "toolkit:import_extraction_review",
                kwargs={"batch_id": self.batch.pk},
            ),
        )

    def test_replacement_approval_explains_why_it_was_blocked(self):
        """The admin is told why, rather than getting a blank error page."""

        response = self._approve("CHANGED_INFORMATION")

        messages = [
            str(message)
            for message in response.wsgi_request._messages
        ]

        self.assertTrue(
            any(
                "Approval blocked:" in message
                for message in messages
            ),
            f"No 'Approval blocked:' message was emitted. Got: {messages}",
        )

    def test_replacement_approval_does_not_create_a_service(self):
        """Blocking must actually prevent the write."""

        before = Service.objects.count()

        self._approve("CHANGED_INFORMATION")

        self.assertEqual(Service.objects.count(), before)

    def test_guard_only_blocks_changed_information(self):
        """A safe delta status must not hit the blocked-approval path."""

        response = self._approve("NEW_INFORMATION")

        # Whatever the downstream flow decides, it must not be the
        # blocked-approval message - otherwise the guard is over-blocking.
        messages = [
            str(message)
            for message in response.wsgi_request._messages
        ]

        self.assertFalse(
            any(
                "Approval blocked:" in message
                for message in messages
            ),
            "A non-CHANGED_INFORMATION row was wrongly blocked.",
        )
