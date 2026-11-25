from datetime import date
from decimal import Decimal

from django.db.models import Sum

from masters.models import Item

from .models import StockMovement
from .services import average_cost


def parse_range(request):
    """Date range from ?from=YYYY-MM-DD&to=YYYY-MM-DD; defaults to this month so far."""
    today = date.today()
    try:
        d1 = date.fromisoformat(request.GET.get("from", ""))
    except ValueError:
        d1 = today.replace(day=1)
    try:
        d2 = date.fromisoformat(request.GET.get("to", ""))
    except ValueError:
        d2 = today
    return d1, d2


def _sum(qs):
    return qs.aggregate(t=Sum("quantity"))["t"] or Decimal("0")


def stock_summary_rows(d1, d2):
    """opening + receipts - issues = closing, per item, from the ledger."""
    rows = []
    items = Item.objects.filter(is_active=True).select_related("base_unit").order_by("kind", "name")
    for item in items:
        qs = StockMovement.objects.filter(item=item)
        period = qs.filter(date__gte=d1, date__lte=d2)
        opening = _sum(qs.filter(date__lt=d1)) + _sum(period.filter(movement_type="OPENING"))
        flow = period.exclude(movement_type="OPENING")
        receipts = _sum(flow.filter(quantity__gt=0))
        issues = -_sum(flow.filter(quantity__lt=0))
        closing = opening + receipts - issues
        if item.kind == "FINISHED":
            from production.models import ProductionRun
            run = ProductionRun.objects.filter(product=item, date__lte=d2).order_by("-date", "-id").first()
            cost = (run.cost_per_packet if run else None) or Decimal("0")
        else:
            cost = average_cost(item, as_of=d2)
        rows.append({
            "kind": item.get_kind_display(), "item": item, "unit": item.base_unit.code,
            "opening": opening, "receipts": receipts, "issues": issues, "closing": closing,
            "avg_cost": cost, "value": (closing * cost).quantize(Decimal("0.01")),
        })
    return rows