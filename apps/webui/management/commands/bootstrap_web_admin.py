import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Creates the initial administrator once, using a runtime secret."

    def handle(self, *args, **options):
        password = os.environ.get("TASKFLOW_ADMIN_PASSWORD")
        if not password:
            return
        username = os.environ.get("TASKFLOW_ADMIN_USERNAME", "taskflow_admin")
        user_model = get_user_model()
        existing = user_model.objects.filter(username=username).first()
        if existing:
            if (
                not existing.is_superuser
                or not existing.is_staff
                or not existing.is_active
            ):
                raise CommandError("The bootstrap username is already in use.")
            return
        user = user_model(username=username)
        try:
            user.full_clean(exclude=["password"])
            if len(password) < 12:
                raise ValidationError("Use at least 12 characters.")
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError(
                "Use a valid username and a strong bootstrap password."
            ) from error
        user_model.objects.create_superuser(username=username, password=password)
        self.stdout.write("Initial web administrator created.")
