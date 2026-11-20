from django.db import models


class Unit(models.Model):
    """to_base converts a unit to the base unit of its dimension: kg, litre, piece."""
    class Dimension(models.TextChoices):
        WEIGHT = "WEIGHT"
        VOLUME = "VOLUME"
        COUNT = "COUNT"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=40)
    dimension = models.CharField(max_length=10, choices=Dimension.choices)
    to_base = models.DecimalField(max_digits=14, decimal_places=6)

    def __str__(self):
        return self.code


class Item(models.Model):
    """Raw materials, packaging and finished goods share one table,
    so the stock ledger works the same way for all three."""
    class Kind(models.TextChoices):
        RAW = "RAW", "Raw material"
        PACKAGING = "PACKAGING", "Packaging"
        FINISHED = "FINISHED", "Finished good"

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    base_unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    hsn_code = models.CharField(max_length=8, blank=True)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    packets_per_carton = models.PositiveIntegerField(null=True, blank=True)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    class Kind(models.TextChoices):
        RETAILER = "RETAILER"
        DISTRIBUTOR = "DISTRIBUTOR"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    gstin = models.CharField(max_length=15, blank=True)
    state_code = models.CharField(max_length=2)  # decides CGST+SGST vs IGST
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=120)
    gstin = models.CharField(max_length=15, blank=True)
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.name


class BOM(models.Model):
    """Bill of Materials: the recipe for one batch of a finished product."""
    product = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="boms",
                                limit_choices_to={"kind": "FINISHED"})
    name = models.CharField(max_length=100)
    expected_yield = models.DecimalField(max_digits=12, decimal_places=4)  # packets per batch
    tolerance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=3)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (yield {self.expected_yield})"


class BOMLine(models.Model):
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT,
                             limit_choices_to={"kind__in": ["RAW", "PACKAGING"]})
    quantity = models.DecimalField(max_digits=14, decimal_places=4)  # per batch
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)