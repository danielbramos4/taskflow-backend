from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


class SignIn(LoginView):
    template_name = "webui/login.html"
    next_page = reverse_lazy("webui:dashboard")
    redirect_authenticated_user = True


class SignOut(LogoutView):
    next_page = reverse_lazy("webui:login")


@require_safe
@never_cache
@login_required(login_url="webui:login")
def dashboard(request):
    return render(request, "webui/dashboard.html")


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
