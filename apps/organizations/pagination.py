from rest_framework.pagination import PageNumberPagination


class OrganizationPagination(PageNumberPagination):
    page_size = 20
