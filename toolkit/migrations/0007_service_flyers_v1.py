# Generated for the BharatNXT Wave guarded flyer workflow.

import django.db.models.deletion
import toolkit.flyer_storage
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("toolkit", "0006_saved_client_collections_v1"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceFlyer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                (
                    "file",
                    models.FileField(
                        max_length=500,
                        storage=toolkit.flyer_storage.PrivateFlyerStorage(),
                        upload_to=(
                            toolkit.flyer_storage.service_flyer_upload_to
                        ),
                    ),
                ),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "file_kind",
                    models.CharField(
                        choices=[("PDF", "PDF"), ("IMAGE", "Image")],
                        max_length=10,
                    ),
                ),
                ("mime_type", models.CharField(max_length=100)),
                ("file_size", models.PositiveBigIntegerField()),
                (
                    "sha256",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                    ),
                ),
                ("service_id_snapshot", models.CharField(max_length=40)),
                (
                    "service_title_snapshot",
                    models.CharField(max_length=255),
                ),
                ("uploaded_by_label", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("update_note", models.CharField(blank=True, max_length=500)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                (
                    "restored_from",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="restored_versions",
                        to="toolkit.serviceflyer",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="flyers",
                        to="toolkit.service",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_service_flyers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-version", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="serviceflyer",
            index=models.Index(
                fields=["service", "is_current"],
                name="toolkit_flyer_current_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="serviceflyer",
            index=models.Index(
                fields=["service", "uploaded_at"],
                name="toolkit_flyer_history_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="serviceflyer",
            constraint=models.UniqueConstraint(
                fields=("service", "version"),
                name="unique_flyer_version_per_service",
            ),
        ),
        migrations.AddConstraint(
            model_name="serviceflyer",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_current=True),
                fields=("service",),
                name="one_current_flyer_per_service",
            ),
        ),
        migrations.AddConstraint(
            model_name="serviceflyer",
            constraint=models.CheckConstraint(
                condition=models.Q(file_size__gt=0),
                name="service_flyer_file_size_positive",
            ),
        ),
    ]
