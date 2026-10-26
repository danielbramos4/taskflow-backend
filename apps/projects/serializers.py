from collections.abc import Mapping

from rest_framework import serializers

from apps.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    allowed_input_fields = {"name", "description"}
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
            unexpected = set(data) - self.allowed_input_fields
            if unexpected:
                raise serializers.ValidationError(
                    {field: ["Campo não permitido."] for field in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if validated_data:
            instance.save(update_fields=[*validated_data, "updated_at"])
        return instance


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid")
        return data


class ProjectUpdateSerializer(ProjectSerializer):
    is_archived = StrictBooleanField(required=False)
    allowed_input_fields = ProjectSerializer.allowed_input_fields | {"is_archived"}

    class Meta(ProjectSerializer.Meta):
        read_only_fields = [
            field
            for field in ProjectSerializer.Meta.read_only_fields
            if field != "is_archived"
        ]
