from django.conf import settings
from django.db import models


class StockMovement(models.Model):
    """Append-only ledger. Balance = sum of quantity. Never edit or delete a row;
    correct mistakes by posting a reversing movement."""

    class Type(models.TextChoices):
        OPENING = "OPENING"
        PURCHASE = "PURCHASE"
        PRODUCTION_ISSUE = "PRODUCTION_ISSUE"
        PRODUCTION_OUTPUT = "PRODUCTION_OUTPUT"
        WASTAGE = "WASTAGE"
        DISPATCH = "DISPATCH"
        SALES_RETURN = "SALES_RETURN"
        ADJUSTMENT = "ADJUSTMENT"

    item = models.ForeignKey("masters.Item", on_delete=models.PROTECT, related_name="movements")
    date = models.DateField()
    movement_type = models.CharField(max_length=20, choices=Type.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)  # + in, - out (item base unit)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    source_type = models.CharField(max_length=30)  # "opening", "purchase", "production_run", "invoice"
    source_id = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Stock ledger rows are immutable; post a reversing entry.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Stock ledger rows cannot be deleted.")

    def __str__(self):
        return f"{self.date} {self.item} {self.quantity}"