from collections.abc import Mapping

from rest_framework import serializers

from apps.tasks.models import Task


class TaskSerializer(serializers.ModelSerializer):
    allowed_input_fields = {"title", "description"}
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


class TaskUpdateSerializer(TaskSerializer):
    status = serializers.ChoiceField(choices=Task.Status.choices, required=False)
    allowed_input_fields = TaskSerializer.allowed_input_fields | {"status"}

    class Meta(TaskSerializer.Meta):
        read_only_fields = [
            field for field in TaskSerializer.Meta.read_only_fields if field != "status"
        ]
