from django.urls import path

from . import views

urlpatterns = [
    path("purchase/new/", views.purchase_new, name="purchase_new"),
    path("stock/", views.stock_summary, name="stock_summary"),
    path("stock/ledger/", views.stock_ledger, name="stock_ledger"),
]