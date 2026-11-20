from decimal import Decimal

from django.db.models import Sum

from .models import StockMovement


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