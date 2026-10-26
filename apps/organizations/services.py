from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.organizations.models import Membership


def create_membership(*, organization, user, role=Membership.Role.MEMBER):
    """Caller must hold the organization row lock in a transaction."""
    if Membership.objects.filter(organization=organization, user=user).exists():
        raise ValidationError({"user_id": ["Usuário já participa da organização."]})
    try:
        with transaction.atomic():
            return Membership.objects.create(
                organization=organization, user=user, role=role
            )
    except IntegrityError:
        if Membership.objects.filter(organization=organization, user=user).exists():
            raise ValidationError(
                {"user_id": ["Usuário já participa da organização."]}
            ) from None
        raise APIException("Não foi possível adicionar o membro.") from None


def ensure_another_active_owner(membership):
    if membership.role == Membership.Role.OWNER and not (
        Membership.objects.filter(
            organization_id=membership.organization_id,
            role=Membership.Role.OWNER,
            user__is_active=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    ):
        raise ValidationError(
            {"role": ["A organização deve manter pelo menos um proprietário ativo."]}
        )


def update_membership_role(membership, role):
    """Caller must hold the organization row lock in a transaction."""
    if role == membership.role:
        return membership
    if role != Membership.Role.OWNER:
        ensure_another_active_owner(membership)
    try:
        with transaction.atomic():
            membership.role = role
            membership.save(update_fields=["role"])
    except IntegrityError:
        raise APIException("Não foi possível atualizar o membro.") from None
    return membership


def delete_membership(membership):
    """Caller must hold the organization row lock in a transaction."""
    ensure_another_active_owner(membership)
    try:
        with transaction.atomic():
            membership.delete()
    except IntegrityError:
        raise APIException("Não foi possível remover o membro.") from None
