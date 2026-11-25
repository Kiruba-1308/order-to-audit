from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("orders/new/", views.order_new, name="order_new"),
    path("orders/mine/", views.my_orders, name="my_orders"),
    path("orders/", views.admin_orders, name="admin_orders"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
        path("invoices/<int:pk>/pdf/", views.invoice_download, name="invoice_pdf"),
]