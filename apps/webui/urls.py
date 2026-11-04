from django.urls import path

from apps.webui.views import SignIn, SignOut, dashboard, health

app_name = "webui"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("entrar/", SignIn.as_view(), name="login"),
    path("sair/", SignOut.as_view(), name="logout"),
    path("health/", health, name="health"),
]
