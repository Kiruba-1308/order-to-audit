from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class Order(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"
        INVOICED = "INVOICED"
        DISPATCHED = "DISPATCHED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT)
    salesman = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name="orders")
    date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    notes = models.CharField(max_length=200, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="approved_orders")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_value(self):
        return sum((l.quantity * l.rate for l in self.lines.all()), Decimal("0"))

    def __str__(self):
        return f"Order {self.pk} - {self.customer} - {self.status}"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("masters.Item", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)  # price per packet before tax


class Invoice(models.Model):
    number = models.CharField(max_length=20, unique=True)  # e.g. 2026-27/0001
    fy = models.CharField(max_length=7)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="invoices")
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT)
    date = models.DateField()
    place_of_supply = models.CharField(max_length=2)  # GST state code
    is_igst = models.BooleanField(default=False)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dispatched_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def paid(self):
        return self.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def outstanding(self):
        return self.total - self.paid

    def __str__(self):
        return self.number


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("masters.Item", on_delete=models.PROTECT)
    hsn_code = models.CharField(max_length=8, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=20, default="CASH")
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)