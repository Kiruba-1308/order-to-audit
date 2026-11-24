from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from masters.units import convert

from .models import Purchase, PurchaseLine, StockMovement


def stock_balance(item, as_of=None):
    """Current balance of an item = sum of all its ledger movements."""
    qs = StockMovement.objects.filter(item=item)
    if as_of:
        qs = qs.filter(date__lte=as_of)
    return qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def post_movement(*, item, date, movement_type, quantity, source_type,
                  source_id=None, unit_cost=None, remarks="", user=None):
    """The only way stock should ever change. Every feature calls this."""
    return StockMovement.objects.create(
        item=item, date=date, movement_type=movement_type, quantity=Decimal(quantity),
        unit_cost=unit_cost, source_type=source_type, source_id=source_id,
        remarks=remarks, created_by=user,
    )


def average_cost(item, as_of=None):
    """Weighted average cost per base unit, replayed from the ledger in order.
    Receipts with a cost raise the average; issues leave it unchanged."""
    qs = StockMovement.objects.filter(item=item)
    if as_of:
        qs = qs.filter(date__lte=as_of)
    qty = value = last = Decimal("0")
    for m in qs.order_by("date", "id"):
        if m.quantity > 0:
            qty += m.quantity
            if m.unit_cost is not None:
                value += m.quantity * m.unit_cost
                last = m.unit_cost
        elif qty > 0:
            value += m.quantity * (value / qty)
            qty += m.quantity
        else:
            qty += m.quantity
    if qty > 0:
        return (value / qty).quantize(Decimal("0.0001"))
    return last


@transaction.atomic
def record_purchase(*, supplier, date, lines, invoice_number="", user=None):
    """lines = [(item, quantity, unit, rate), ...]. Quantity and rate are in `unit`;
    the ledger stores the item's base unit."""
    purchase = Purchase.objects.create(supplier=supplier, date=date,
                                       invoice_number=invoice_number, created_by=user)
    for item, qty, unit, rate in lines:
        qty, rate = Decimal(str(qty)), Decimal(str(rate))
        factor = convert(1, unit, item.base_unit)
        PurchaseLine.objects.create(purchase=purchase, item=item, quantity=qty,
                                    unit=unit, rate=rate)
        post_movement(item=item, date=date, movement_type=StockMovement.Type.PURCHASE,
                      quantity=qty * factor,
                      unit_cost=(rate / factor).quantize(Decimal("0.0001")),
                      source_type="purchase", source_id=purchase.id)
    return purchase