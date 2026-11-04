from rest_framework import serializers

from apps.tasks.serializers import ISODateField


class TaskFilters(serializers.Serializer):
    assignee_membership_id = serializers.RegexField(
        r"\A(?:unassigned|[1-9][0-9]{0,18})\Z", required=False, trim_whitespace=False
    )
    due_from = ISODateField(required=False)
    due_to = ISODateField(required=False)

    def to_internal_value(self, data):
        repeated = {
            name: ["Informe apenas um valor."]
            for name in self.fields
            if len(data.getlist(name)) > 1
        }
        if repeated:
            raise serializers.ValidationError(repeated)
        return super().to_internal_value(
            {name: data[name] for name in self.fields if name in data}
        )

    def validate_assignee_membership_id(self, value):
        if value == "unassigned":
            return None
        membership_id = int(value)
        if membership_id > 2**63 - 1:
            raise serializers.ValidationError("Identificador fora do intervalo.")
        return membership_id

    def validate(self, attrs):
        if {"due_from", "due_to"} <= attrs.keys() and attrs["due_from"] > attrs[
            "due_to"
        ]:
            raise serializers.ValidationError(
                {"due_to": "Deve ser igual ou posterior a due_from."}
            )
        return attrs

    def apply(self, queryset):
        filters = {
            "assignee_membership_id": "assignee_id",
            "due_from": "due_date__gte",
            "due_to": "due_date__lte",
        }
        return queryset.filter(
            **{filters[field]: value for field, value in self.validated_data.items()}
        )
