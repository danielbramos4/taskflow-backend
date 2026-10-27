from collections.abc import Mapping

from rest_framework import serializers

from apps.tasks.models import Task


class TaskSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(read_only=True)
    created_by_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "project_id",
            "title",
            "description",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project_id",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = set(data) - {"title", "description"}
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
