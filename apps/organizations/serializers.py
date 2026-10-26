from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.organizations.models import Membership, Organization
from apps.organizations.services import create_membership, update_membership_role


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.ReadOnlyField()

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "my_role", "created_at", "updated_at"]
        read_only_fields = ["id", "my_role", "created_at", "updated_at"]

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = set(data) - {"name", "slug"}
            if unexpected:
                raise serializers.ValidationError(
                    {field: ["Campo não permitido."] for field in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def create(self, validated_data):
        try:
            with transaction.atomic():
                organization = Organization.objects.create(**validated_data)
                Membership.objects.create(
                    organization=organization,
                    user=self.context["request"].user,
                    role=Membership.Role.OWNER,
                )
        except IntegrityError:
            # A concurrent request can claim the slug after serializer validation.
            if Organization.objects.filter(slug=validated_data["slug"]).exists():
                raise serializers.ValidationError(
                    {"slug": ["Já existe uma organização com este slug."]}
                ) from None
            raise APIException("Não foi possível criar a organização.") from None

        organization.my_role = Membership.Role.OWNER
        return organization

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                for field, value in validated_data.items():
                    setattr(instance, field, value)
                if validated_data:
                    instance.save(update_fields=[*validated_data, "updated_at"])
        except IntegrityError:
            if "slug" in validated_data and (
                Organization.objects.filter(slug=validated_data["slug"])
                .exclude(pk=instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"slug": ["Já existe uma organização com este slug."]}
                ) from None
            raise APIException("Não foi possível atualizar a organização.") from None

        return instance


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=get_user_model().objects.filter(is_active=True)
    )
    username = serializers.ReadOnlyField(source="user.username")
    role = serializers.ChoiceField(
        choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )

    class Meta:
        model = Membership
        fields = ["id", "user_id", "username", "role", "created_at"]
        read_only_fields = ["id", "username", "created_at"]

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            allowed = {"user_id", "role"} if self.instance is None else {"role"}
            unexpected = set(data) - allowed
            if unexpected:
                raise serializers.ValidationError(
                    {field: ["Campo não permitido."] for field in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def create(self, validated_data):
        return create_membership(**validated_data)

    def update(self, instance, validated_data):
        return update_membership_role(
            instance, validated_data.get("role", instance.role)
        )
