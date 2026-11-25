from django.urls import path

from . import views

urlpatterns = [
    path("production/", views.run_list, name="run_list"),
    path("production/new/", views.run_new, name="run_new"),
    path("production/<int:pk>/", views.run_detail, name="run_detail"),
    path("production/<int:pk>/costs/", views.run_costs, name="run_costs"),
]