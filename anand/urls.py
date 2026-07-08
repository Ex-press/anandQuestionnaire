from django.contrib import admin
from django.urls import include, path

from screening import views as screening_views

urlpatterns = [
    path("", screening_views.index, name="index"),
    path("admin/", admin.site.urls),
    path("sms/", include("screening.urls")),
    path("consent", screening_views.consent_proof, name="consent"),
]
