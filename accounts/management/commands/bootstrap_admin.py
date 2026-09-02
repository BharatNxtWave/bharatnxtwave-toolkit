"""Create the first administrator when there is no shell to do it from.

A free Render instance has no Shell, so `createsuperuser` cannot be run by
hand there. This creates the first admin from environment variables during
container start instead.

It is deliberately narrow:

  * it does nothing at all once any superuser exists, so it is safe to leave
    configured across deploys;
  * it never changes an existing user's password;
  * it refuses a weak password, because this account has full access.

Remove the variables from the service configuration once you have signed in -
they are a password sitting in a settings page.

    BHARATNXT_BOOTSTRAP_ADMIN_USERNAME=admin
    BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD=<a long random password>
    BHARATNXT_BOOTSTRAP_ADMIN_EMAIL=admin@example.com   # optional
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    ValidationError,
    validate_password,
)
from django.core.management.base import BaseCommand


MIN_PASSWORD_LENGTH = 12


class Command(BaseCommand):
    help = "Create the first SUPER_ADMIN from environment variables."

    def handle(self, *args, **options):
        User = get_user_model()

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                "A superuser already exists; nothing to do."
            )
            return

        username = os.environ.get(
            "BHARATNXT_BOOTSTRAP_ADMIN_USERNAME", ""
        ).strip()

        password = os.environ.get(
            "BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD", ""
        )

        email = os.environ.get(
            "BHARATNXT_BOOTSTRAP_ADMIN_EMAIL", ""
        ).strip()

        if not username or not password:
            self.stderr.write(
                "BHARATNXT_BOOTSTRAP_ADMIN_USERNAME and "
                "BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD must both be set."
            )
            return

        if len(password) < MIN_PASSWORD_LENGTH:
            self.stderr.write(
                f"Refusing to create an administrator with a password "
                f"shorter than {MIN_PASSWORD_LENGTH} characters."
            )
            return

        try:
            validate_password(password)

        except ValidationError as exc:
            self.stderr.write(
                "Refusing to create an administrator: "
                + " ".join(exc.messages)
            )
            return

        if User.objects.filter(username=username).exists():
            # Someone reused an existing BDE username. Promoting it silently
            # would be a surprising privilege change.
            self.stderr.write(
                f"User {username!r} already exists but is not a superuser. "
                "Refusing to change it. Pick a different username."
            )
            return

        User.objects.create_superuser(
            username=username,
            email=email or "",
            password=password,
            role="SUPER_ADMIN",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created administrator {username!r}. "
                "Remove the BHARATNXT_BOOTSTRAP_ADMIN_* variables now."
            )
        )
