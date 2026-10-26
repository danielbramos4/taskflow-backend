from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.organizations.models import Membership


class IsOrganizationOwnerOrReadOnly(BasePermission):
    message = "Somente proprietários podem editar a organização."

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.my_role == Membership.Role.OWNER
