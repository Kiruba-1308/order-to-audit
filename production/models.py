from decimal import Decimal

from django.conf import settings
from django.db import models


class ProductionRun(models.Model):
    product = models.ForeignKey("masters.Item", on_delete=models.PROTECT, related_name="runs")
    bom = models.ForeignKey("masters.BOM", on_delete=models.PROTECT)
    date = models.DateField()
    batches = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    expected_output = models.DecimalField(max_digits=12, decimal_places=4)
    actual_output = models.DecimalField(max_digits=12, decimal_places=4)
    yield_variance_pct = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    yield_flagged = models.BooleanField(default=False)
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    labour_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_cost(self):
        return self.material_cost + self.labour_cost + self.overhead_cost

    @property
    def cost_per_packet(self):
        if not self.actual_output:
            return None
        return (self.total_cost / self.actual_output).quantize(Decimal("0.01"))

    def __str__(self):
        return f"Run {self.pk} - {self.product} - {self.date}"


class ProductionRunLine(models.Model):
    run = models.ForeignKey(ProductionRun, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("masters.Item", on_delete=models.PROTECT)
    planned_qty = models.DecimalField(max_digits=14, decimal_places=4)
    issued_qty = models.DecimalField(max_digits=14, decimal_places=4)
    wastage_qty = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    variance_pct = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    flagged = models.BooleanField(default=False)

    @property
    def actual_qty(self):
        return self.issued_qty + self.wastage_qty