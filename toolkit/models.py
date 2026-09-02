from django.conf import settings
from django.db import models

# BNW_SERVICE_FLYER_V1
from .flyer_storage import (
    private_flyer_storage,
    service_flyer_upload_to,
)


# =========================================================
# SERVICE DOMAIN
# Examples:
# Government Schemes & Grants
# Business Incorporation & Launch
# Compliance Management
# Funding & Equity Support
# =========================================================

class ServiceDomain(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True
    )

    slug = models.SlugField(
        max_length=170,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


# =========================================================
# CATEGORY
# Examples:
# Company Registration
# Government Grants
# MSME Loans
# Certifications
# =========================================================

class Category(models.Model):
    domain = models.ForeignKey(
        ServiceDomain,
        on_delete=models.PROTECT,
        related_name="categories"
    )

    name = models.CharField(
        max_length=150
    )

    slug = models.SlugField(
        max_length=170
    )

    description = models.TextField(
        blank=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["display_order", "name"]

        constraints = [
            models.UniqueConstraint(
                fields=["domain", "slug"],
                name="unique_category_slug_per_domain"
            )
        ]

    def __str__(self):
        return f"{self.domain.name} → {self.name}"


# =========================================================
# MAIN SERVICE / SCHEME
# Examples:
# Startup India
# PMEGP
# CGTMSE
# Pvt Ltd Registration
# ISO Certification
# FSSAI Licence
# =========================================================

class Service(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("UNDER_REVIEW", "Under Review"),
        ("APPROVED", "Approved"),
        ("PUBLISHED", "Published"),
        ("EXPIRING", "Expiring"),
        ("ARCHIVED", "Archived"),
    ]

    SERVICE_KIND_CHOICES = [
        ("REGISTRATION", "Registration"),
        ("COMPLIANCE", "Compliance"),
        ("CERTIFICATION", "Certification"),
        ("GOVT_SCHEME", "Government Scheme"),
        ("GRANT", "Grant"),
        ("LOAN", "Loan"),
        ("DEBT", "Debt Funding"),
        ("EQUITY", "Equity Funding"),
        ("VC", "VC Funding"),
        ("SUBSIDY", "Subsidy"),
        ("LEGAL", "Legal Service"),
        ("DIGITAL", "Digital Service"),
        ("CONSULTING", "Consulting"),
        ("OTHER", "Other"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("NORMAL", "Normal"),
        ("HIGH", "High"),
        ("CRITICAL", "Critical"),
    ]

    # -----------------------------
    # Identity
    # -----------------------------

    service_id = models.CharField(
        max_length=40,
        unique=True
    )

    title = models.CharField(
        max_length=255
    )

    slug = models.SlugField(
        max_length=280,
        unique=True
    )

    domain = models.ForeignKey(
        ServiceDomain,
        on_delete=models.PROTECT,
        related_name="services"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="services"
    )

    # Primary category remains above for backward compatibility.
    # This relationship allows one real Service to also belong
    # to multiple workbook classifications without duplication.
    classifications = models.ManyToManyField(
        Category,
        through="ServiceClassification",
        related_name="classified_services",
        blank=True
    )

    service_kind = models.CharField(
        max_length=30,
        choices=SERVICE_KIND_CHOICES
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="NORMAL"
    )

    # -----------------------------
    # BDE-facing information
    # -----------------------------

    bde_summary = models.TextField(
        blank=True,
        help_text="Short explanation BDE can quickly read during a call."
    )

    overview = models.TextField(
        blank=True
    )

    benefits = models.TextField(
        blank=True
    )

    restrictions = models.TextField(
        blank=True
    )

    important_notes = models.TextField(
        blank=True
    )

    # -----------------------------
    # Eligibility information
    # -----------------------------

    eligibility_summary = models.TextField(
        blank=True
    )

    business_types = models.JSONField(
        default=list,
        blank=True
    )

    business_stages = models.JSONField(
        default=list,
        blank=True
    )

    industries = models.JSONField(
        default=list,
        blank=True
    )

    applicable_states = models.JSONField(
        default=list,
        blank=True
    )

    founder_categories = models.JSONField(
        default=list,
        blank=True
    )

    # Original source value is retained because "Applicable for"
    # may contain business type, founder category, stage, state,
    # or mixed eligibility information.
    applicable_for_raw = models.TextField(
        blank=True
    )

    min_business_age_months = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    max_business_age_months = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    min_turnover = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True
    )

    max_turnover = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True
    )

    # -----------------------------
    # Funding / financial details
    # -----------------------------

    funding_min = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True
    )

    funding_max = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True
    )

    funding_type = models.CharField(
        max_length=120,
        blank=True
    )

    funding_organisation = models.CharField(
        max_length=255,
        blank=True
    )

    interest_rate_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    interest_rate_max = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    collateral_required = models.BooleanField(
        null=True,
        blank=True
    )

    tenure = models.CharField(
        max_length=150,
        blank=True
    )

    subsidy_details = models.TextField(
        blank=True
    )

    # -----------------------------
    # BharatNXT commercial info
    # -----------------------------

    government_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    bharatnxt_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    pricing_notes = models.TextField(
        blank=True
    )

    # -----------------------------
    # Timeline
    # -----------------------------

    estimated_processing_time = models.CharField(
        max_length=150,
        blank=True
    )

    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="Date from which BDEs should start pitching this service."
    )

    pitch_until = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Internal last date until which BDEs should pitch this service."
    )

    application_deadline = models.DateField(
        null=True,
        blank=True
    )

    DEADLINE_STATUS_CHOICES = [
        ("UNKNOWN", "Unknown"),
        ("DATED", "Specific Date"),
        ("ROLLING", "Rolling"),
        ("ONGOING", "Ongoing"),
        ("OPEN", "Open"),
        ("CLOSED", "Closed"),
        ("NO_DEADLINE", "No Deadline"),
        ("OTHER", "Other"),
    ]

    # Preserve the exact source text. application_deadline is
    # populated only when the value can be confidently normalized.
    application_deadline_raw = models.TextField(
        blank=True
    )

    deadline_status = models.CharField(
        max_length=20,
        choices=DEADLINE_STATUS_CHOICES,
        default="UNKNOWN",
        db_index=True
    )

    # -----------------------------
    # Internal company information
    # -----------------------------

    internal_notes = models.TextField(
        blank=True
    )

    sales_pitch = models.TextField(
        blank=True
    )

    escalation_notes = models.TextField(
        blank=True
    )

    # -----------------------------
    # Verification
    # -----------------------------

    version = models.PositiveIntegerField(
        default=1
    )

    last_verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_services"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_services"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["title"]

        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["service_kind"]),
            models.Index(fields=["domain"]),
            models.Index(fields=["category"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["last_verified_at"]),
        ]

    def __str__(self):
        return f"{self.service_id} - {self.title}"


# =========================================================
# ELIGIBILITY RULE
# Allows multiple clean eligibility conditions
# instead of one giant paragraph.
# =========================================================

class EligibilityRule(models.Model):

    RULE_TYPE_CHOICES = [
        ("REQUIRED", "Required"),
        ("OPTIONAL", "Optional"),
        ("DISQUALIFIER", "Disqualifier"),
        ("INFORMATION", "Information"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="eligibility_rules"
    )

    rule_type = models.CharField(
        max_length=20,
        choices=RULE_TYPE_CHOICES,
        default="REQUIRED"
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField()

    display_order = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.service.title} - {self.title}"


# =========================================================
# DOCUMENT REQUIREMENTS
# =========================================================

class DocumentRequirement(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="document_requirements"
    )

    name = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True
    )

    is_mandatory = models.BooleanField(
        default=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.service.title} - {self.name}"


# =========================================================
# PROCESS STEPS
# Example:
# 1. Eligibility check
# 2. Document collection
# 3. Application
# 4. Approval
# =========================================================

class ProcessStep(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="process_steps"
    )

    step_number = models.PositiveIntegerField()

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True
    )

    estimated_time = models.CharField(
        max_length=120,
        blank=True
    )

    class Meta:
        ordering = ["step_number"]

        constraints = [
            models.UniqueConstraint(
                fields=["service", "step_number"],
                name="unique_step_number_per_service"
            )
        ]

    def __str__(self):
        return f"{self.service.title} - Step {self.step_number}"


# =========================================================
# SOURCES
# Official links / verification references
# =========================================================

class ServiceSource(models.Model):

    SOURCE_KIND_CHOICES = [
        ("OFFICIAL_PORTAL", "Official Portal"),
        ("APPLICATION", "Application Link"),
        ("FLYER", "Flyer"),
        ("REFERENCE", "Reference"),
        ("OTHER", "Other"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="sources"
    )

    source_name = models.CharField(
        max_length=255
    )

    source_url = models.URLField(
        max_length=1000,
        blank=True
    )

    source_kind = models.CharField(
        max_length=30,
        choices=SOURCE_KIND_CHOICES,
        default="REFERENCE",
        db_index=True
    )

    # Optional row-level provenance for imported workbook data.
    import_row = models.ForeignKey(
        "ImportRow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_sources"
    )

    source_reference = models.CharField(
        max_length=255,
        blank=True
    )

    is_official = models.BooleanField(
        default=False
    )

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    notes = models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.service.title} - {self.source_name}"


# =========================================================
# RELATED SERVICES
#
# Example:
# Startup India → Udyam → GST → Funding Scheme
# =========================================================

class RelatedService(models.Model):

    RELATION_CHOICES = [
        ("RECOMMENDED", "Recommended"),
        ("PREREQUISITE", "Prerequisite"),
        ("ALTERNATIVE", "Alternative"),
        ("FOLLOW_UP", "Follow-up Service"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="related_from"
    )

    related_service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="related_to"
    )

    relation_type = models.CharField(
        max_length=20,
        choices=RELATION_CHOICES,
        default="RECOMMENDED"
    )

    notes = models.TextField(
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "service",
                    "related_service",
                    "relation_type"
                ],
                name="unique_service_relationship"
            )
        ]

    def __str__(self):
        return (
            f"{self.service.title} → "
            f"{self.related_service.title}"
        )


# =========================================================
# SEARCH EVENT
# Structured search analytics for BDE dashboards.
# This is separate from ActivityLog because analytics
# should not depend on parsing human-readable audit text.
# =========================================================

class SearchEvent(models.Model):

    EVENT_CHOICES = [
        ("SEARCH", "Search"),
        ("SUGGESTION_CLICK", "Suggestion Click"),
        ("FILTER", "Filter"),
        ("CLIENT_MATCH", "Client Match"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="toolkit_search_events"
    )

    event_type = models.CharField(
        max_length=30,
        choices=EVENT_CHOICES,
        default="SEARCH"
    )

    query = models.CharField(
        max_length=255,
        blank=True
    )

    filters = models.JSONField(
        default=dict,
        blank=True
    )

    result_count = models.PositiveIntegerField(
        default=0
    )

    selected_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_selections"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["user", "created_at"]
            ),
            models.Index(
                fields=["event_type", "created_at"]
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.event_type} - "
            f"{self.query}"
        )


# =========================================================
# SAVED SERVICE
# Personal starred/saved toolkit services for each BDE.
# =========================================================

class SavedService(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_toolkit_services"
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="saved_by_users"
    )

    note = models.CharField(
        max_length=500,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "service"],
                name="unique_saved_service_per_user"
            )
        ]

        indexes = [
            models.Index(
                fields=["user", "created_at"]
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} → "
            f"{self.service.service_id}"
        )




# =========================================================
# BNX_SAVED_COLLECTIONS_V1
# CLIENT / SAVED COLLECTIONS
#
# SavedService remains the global bookmark owned by a BDE.
# A single SavedService can be placed into multiple client
# collections without duplicating the underlying bookmark.
# =========================================================

class SavedCollection(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="toolkit_saved_collections",
    )

    name = models.CharField(
        max_length=150,
    )

    note = models.CharField(
        max_length=500,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "-updated_at",
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "name",
                ],
                name=(
                    "unique_saved_collection_"
                    "name_per_user"
                ),
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "updated_at",
                ]
            ),
        ]

    def __str__(self):

        return (
            f"{self.user.username} → "
            f"{self.name}"
        )


class SavedCollectionItem(models.Model):

    collection = models.ForeignKey(
        SavedCollection,
        on_delete=models.CASCADE,
        related_name="items",
    )

    saved_service = models.ForeignKey(
        SavedService,
        on_delete=models.CASCADE,
        related_name="collection_items",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        ordering = [
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "collection",
                    "saved_service",
                ],
                name=(
                    "unique_saved_service_"
                    "per_collection"
                ),
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "collection",
                    "created_at",
                ]
            ),
        ]

    def __str__(self):

        return (
            f"{self.collection.name} → "
            f"{self.saved_service.service.service_id}"
        )


# =========================================================
# IMPORT BATCH
# Metadata/audit history for Excel, CSV and Google Sheets.
#
# IMPORTANT:
# This stores import metadata, NOT the original uploaded
# confidential spreadsheet file.
# =========================================================

class ImportBatch(models.Model):

    SOURCE_CHOICES = [
        ("XLSX", "Excel"),
        ("CSV", "CSV"),
        ("GOOGLE_SHEET", "Google Sheet"),
    ]

    STATUS_CHOICES = [
        ("PREVIEWED", "Previewed"),
        ("VALIDATED", "Validated"),
        # Approved by an admin and waiting for the import worker to pick it
        # up. Applying an import snapshots the whole database and rewrites
        # the catalogue, which is far too long to hold an HTTP request open.
        ("QUEUED", "Queued for import"),
        ("IMPORTING", "Importing"),
        ("IMPORTED", "Imported"),
        ("ROLLED_BACK", "Rolled Back"),
        ("FAILED", "Failed"),
    ]

    source_type = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES
    )

    source_name = models.CharField(
        max_length=255
    )

    source_identifier = models.CharField(
        max_length=500,
        blank=True
    )

    source_modified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    file_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True
    )

    sheet_count = models.PositiveIntegerField(
        default=0
    )

    row_count = models.PositiveIntegerField(
        default=0
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="PREVIEWED"
    )

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="toolkit_import_batches"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    imported_at = models.DateTimeField(
        null=True,
        blank=True
    )

    rolled_back_at = models.DateTimeField(
        null=True,
        blank=True
    )

    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="toolkit_rolled_back_import_batches"
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["source_type", "created_at"]
            ),
            models.Index(
                fields=["status", "created_at"]
            ),
        ]

    def __str__(self):
        return (
            f"{self.source_type} - "
            f"{self.source_name} - "
            f"{self.created_at}"
        )


# ============================================================
# BHARATNXT WORKBOOK IMPORT ARCHITECTURE V1
# ============================================================


class ImportRow(models.Model):

    VALIDATION_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("VALID", "Valid"),
        ("WARNING", "Warning"),
        ("INVALID", "Invalid"),
        ("PROCESSED", "Processed"),
    ]

    CANDIDATE_ACTION_CHOICES = [
        ("UNDECIDED", "Undecided"),
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("MERGE_REVIEW", "Merge Review"),
        ("SKIP", "Skip"),
        ("INVALID", "Invalid"),
    ]

    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="rows"
    )

    sheet_name = models.CharField(
        max_length=255,
        db_index=True
    )

    source_row_number = models.PositiveIntegerField()

    source_key = models.CharField(
        max_length=255,
        blank=True,
        db_index=True
    )

    row_hash = models.CharField(
        max_length=64,
        db_index=True
    )

    # JSON-safe representation of the source row.
    # Import code must convert dates/formulas/etc. to safe values.
    raw_data = models.JSONField(
        default=dict,
        blank=True
    )

    validation_status = models.CharField(
        max_length=20,
        choices=VALIDATION_STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )

    validation_errors = models.JSONField(
        default=list,
        blank=True
    )

    validation_warnings = models.JSONField(
        default=list,
        blank=True
    )

    candidate_action = models.CharField(
        max_length=20,
        choices=CANDIDATE_ACTION_CHOICES,
        default="UNDECIDED",
        db_index=True
    )

    matched_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_import_rows"
    )

    imported_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imported_source_rows"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Explicit source-row accounting after the controlled workbook import.
    # One source row may legitimately produce multiple outcomes.
    import_outcomes = models.JSONField(
        default=list,
        blank=True
    )

    class Meta:
        ordering = [
            "import_batch",
            "sheet_name",
            "source_row_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "import_batch",
                    "sheet_name",
                    "source_row_number",
                ],
                name="unique_import_row_per_sheet"
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "import_batch",
                    "validation_status",
                ]
            ),
            models.Index(
                fields=[
                    "import_batch",
                    "candidate_action",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.import_batch_id} - "
            f"{self.sheet_name} - "
            f"row {self.source_row_number}"
        )


class ServiceClassification(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="classification_links"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="service_classification_links"
    )

    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_classifications"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "service",
                    "category",
                ],
                name="unique_service_classification"
            )
        ]

    def __str__(self):
        return (
            f"{self.service.title} → "
            f"{self.category.name}"
        )


class ServiceCommercial(models.Model):

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE_ALLOWED", "BDE Allowed"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="commercial_terms"
    )

    label = models.CharField(
        max_length=255,
        blank=True
    )

    minimum_charge_raw = models.TextField(
        blank=True
    )

    minimum_charge = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    government_fee_raw = models.TextField(
        blank=True
    )

    government_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    vendor_cost_raw = models.TextField(
        blank=True
    )

    vendor_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    bdm_deduction_raw = models.TextField(
        blank=True
    )

    bdm_deduction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    remarks = models.TextField(
        blank=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_terms"
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.service.title} - "
            f"{self.label or 'Commercial'}"
        )


class ServiceContentSection(models.Model):

    SECTION_TYPE_CHOICES = [
        ("OVERVIEW", "Overview"),
        ("BENEFITS", "Benefits"),
        ("ELIGIBILITY", "Eligibility"),
        ("FUNDING", "Funding"),
        ("SCOPE", "Scope of Work"),
        ("PROCESS", "Process"),
        ("DOCUMENTS", "Documents"),
        ("TIMELINE", "Timeline"),
        ("NOTES", "Notes"),
        ("GLOSSARY", "Glossary"),
        ("COMMERCIAL", "Commercial"),
        ("OTHER", "Other"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="content_sections"
    )

    section_type = models.CharField(
        max_length=20,
        choices=SECTION_TYPE_CHOICES,
        default="OTHER",
        db_index=True
    )

    title = models.CharField(
        max_length=255,
        blank=True
    )

    content = models.TextField()

    display_order = models.PositiveIntegerField(
        default=0
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_sections"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = [
            "display_order",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.service.title} - "
            f"{self.title or self.section_type}"
        )


class ImportChange(models.Model):

    ACTION_CHOICES = [
        ("SERVICE_CREATE", "Service Create"),
        ("SERVICE_UPDATE", "Service Update"),
        ("CLASSIFICATION_ADD", "Classification Add"),
        ("SOURCE_ADD", "Source Add"),
        ("COMMERCIAL_CREATE", "Commercial Create"),
        ("COMMERCIAL_UPDATE", "Commercial Update"),
        ("CONTENT_CREATE", "Content Create"),
        ("REFERENCE_CREATE", "Reference Create"),
        ("OTHER", "Other"),
    ]

    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.PROTECT,
        related_name="changes"
    )

    import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="changes"
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_changes"
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True
    )

    # Generic destination identity makes every created object reversible,
    # including Categories, comparisons, knowledge and communications.
    object_model = models.CharField(
        max_length=120,
        blank=True
    )

    object_pk = models.CharField(
        max_length=80,
        blank=True
    )

    before_snapshot = models.JSONField(
        default=dict,
        blank=True
    )

    after_snapshot = models.JSONField(
        default=dict,
        blank=True
    )

    is_reversed = models.BooleanField(
        default=False,
        db_index=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    reversed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = [
            "created_at",
            "id",
        ]

    def __str__(self):
        return (
            f"Batch {self.import_batch_id} - "
            f"{self.action}"
        )


class ReferenceItem(models.Model):

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    dataset_name = models.CharField(
        max_length=150,
        db_index=True
    )

    key = models.CharField(
        max_length=255,
        blank=True
    )

    value = models.TextField()

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reference_items"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.dataset_name} - "
            f"{self.key or self.pk}"
        )


class ComparisonMatrix(models.Model):

    name = models.CharField(
        max_length=255
    )

    source_sheet = models.CharField(
        max_length=255,
        blank=True
    )

    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparison_matrices"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.name


class ComparisonEntry(models.Model):

    matrix = models.ForeignKey(
        ComparisonMatrix,
        on_delete=models.CASCADE,
        related_name="entries"
    )

    row_number = models.PositiveIntegerField()

    column_name = models.CharField(
        max_length=255
    )

    row_label = models.CharField(
        max_length=255,
        blank=True
    )

    value_raw = models.TextField(
        blank=True
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparison_entries"
    )

    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparison_entries"
    )

    class Meta:
        ordering = [
            "row_number",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "matrix",
                    "row_number",
                    "column_name",
                ],
                name="unique_comparison_matrix_cell"
            )
        ]

    def __str__(self):
        return (
            f"{self.matrix.name} - "
            f"{self.row_number}:{self.column_name}"
        )


class CommunicationTemplate(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("ACTIVE", "Active"),
        ("ARCHIVED", "Archived"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    template_key = models.CharField(
        max_length=120,
        unique=True
    )

    title = models.CharField(
        max_length=255
    )

    subject = models.CharField(
        max_length=255,
        blank=True
    )

    body = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_templates"
    )

    source_sheet = models.CharField(
        max_length=255,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.title



# ============================================================
# KNOWLEDGE DOCUMENTS
# Dedicated storage for source knowledge that is not safely attributable
# to one Service. Service linkage is deliberately optional.
# ============================================================

class KnowledgeDocument(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("ACTIVE", "Active"),
        ("ARCHIVED", "Archived"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    document_key = models.CharField(
        max_length=180,
        unique=True
    )

    title = models.CharField(
        max_length=255
    )

    source_sheet = models.CharField(
        max_length=255,
        db_index=True
    )

    source_import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_documents"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["title", "id"]

    def __str__(self):
        return self.title


class KnowledgeSection(models.Model):

    SECTION_TYPE_CHOICES = [
        ("OVERVIEW", "Overview"),
        ("BENEFITS", "Benefits"),
        ("ELIGIBILITY", "Eligibility"),
        ("FUNDING", "Funding"),
        ("SCOPE", "Scope of Work"),
        ("PROCESS", "Process"),
        ("DOCUMENTS", "Documents"),
        ("TIMELINE", "Timeline"),
        ("NOTES", "Notes"),
        ("GLOSSARY", "Glossary"),
        ("COMMERCIAL", "Commercial"),
        ("OTHER", "Other"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="sections"
    )

    linked_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_sections"
    )

    section_type = models.CharField(
        max_length=20,
        choices=SECTION_TYPE_CHOICES,
        default="OTHER",
        db_index=True
    )

    title = models.CharField(
        max_length=255,
        blank=True
    )

    content = models.TextField()

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_heading = models.BooleanField(
        default=False
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_row = models.OneToOneField(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_section"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["document", "display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "display_order"],
                name="unique_knowledge_section_order_per_document"
            )
        ]

    def __str__(self):
        return (
            f"{self.document.title} - "
            f"{self.title or self.section_type}"
        )


# BNW_SERVICE_FLYER_V1
class ServiceFlyer(models.Model):

    FILE_KIND_CHOICES = [
        ("PDF", "PDF"),
        ("IMAGE", "Image"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="flyers",
    )

    version = models.PositiveIntegerField()

    file = models.FileField(
        storage=private_flyer_storage,
        upload_to=service_flyer_upload_to,
        max_length=500,
    )

    original_filename = models.CharField(
        max_length=255,
    )

    file_kind = models.CharField(
        max_length=10,
        choices=FILE_KIND_CHOICES,
    )

    mime_type = models.CharField(
        max_length=100,
    )

    file_size = models.PositiveBigIntegerField()

    sha256 = models.CharField(
        max_length=64,
        db_index=True,
    )

    service_id_snapshot = models.CharField(
        max_length=40,
    )

    service_title_snapshot = models.CharField(
        max_length=255,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_service_flyers",
    )

    uploaded_by_label = models.CharField(
        max_length=255,
        blank=True,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    update_note = models.CharField(
        max_length=500,
        blank=True,
    )

    restored_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restored_versions",
    )

    is_current = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-version", "-id"]
        indexes = [
            models.Index(
                fields=["service", "is_current"],
                name="toolkit_flyer_current_idx",
            ),
            models.Index(
                fields=["service", "uploaded_at"],
                name="toolkit_flyer_history_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "version"],
                name="unique_flyer_version_per_service",
            ),
            models.UniqueConstraint(
                fields=["service"],
                condition=models.Q(is_current=True),
                name="one_current_flyer_per_service",
            ),
            models.CheckConstraint(
                condition=models.Q(file_size__gt=0),
                name="service_flyer_file_size_positive",
            ),
        ]

    def __str__(self):
        return (
            f"{self.service.service_id} - "
            f"flyer v{self.version}"
        )
