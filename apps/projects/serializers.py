from collections.abc import Mapping

from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(read_only=True)
    created_by_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "organization_id",
            "name",
            "description",
            "is_archived",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization_id",
            "is_archived",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = set(data) - {"name", "description"}
            if unexpected:
                raise serializers.ValidationError(
                    {field: ["Campo não permitido."] for field in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return Project.objects.create(**validated_data)
        except IntegrityError:
            raise APIException("Não foi possível criar o projeto.") from None
