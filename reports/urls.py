from django.urls import path

from . import views

urlpatterns = [
    path("reports/", views.index, name="reports"),
    path("reports/<slug:name>.csv", views.download, name="report_download"),
    path("dashboard/", views.dashboard, name="dashboard"),
]