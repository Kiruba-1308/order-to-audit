from decimal import ROUND_HALF_UP
from decimal import Decimal as D

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import StockMovement
from inventory.services import average_cost, post_movement, stock_balance
from masters.units import convert

from .models import ProductionRun, ProductionRunLine


def variance_pct(actual, planned):
    """Percent difference of actual against planned (negative = less than planned)."""
    if planned == 0:
        return D("0.00")
    return ((actual - planned) / planned * 100).quantize(D("0.01"), ROUND_HALF_UP)


@transaction.atomic
def post_production_run(*, bom, date, actual_output, issues, wastage=None,
                        batches=1, user=None):
    """issues / wastage: {Item: quantity in that BOM line's unit}.
    Everything happens in one transaction: if stock is short, nothing is saved."""
    wastage = wastage or {}
    batches = D(str(batches))
    actual_output = D(str(actual_output))

    bom_items = {line.item for line in bom.lines.all()}
    extra = (set(issues) | set(wastage)) - bom_items
    if extra:
        raise ValidationError("Items not in the BOM: " + ", ".join(i.name for i in extra))

    expected = bom.expected_yield * batches
    yield_var = variance_pct(actual_output, expected)
    run = ProductionRun.objects.create(
        product=bom.product, bom=bom, date=date, batches=batches,
        expected_output=expected, actual_output=actual_output,
        yield_variance_pct=yield_var,
        yield_flagged=abs(yield_var) > bom.tolerance_pct,
        created_by=user)

    material_cost = D("0")
    for line in bom.lines.select_related("item", "unit", "item__base_unit"):
        item = line.item
        base = item.base_unit
        planned = convert(line.quantity * batches, line.unit, base)
        issued = convert(D(str(issues.get(item, 0))), line.unit, base)
        wasted = convert(D(str(wastage.get(item, 0))), line.unit, base)
        used = issued + wasted

        available = stock_balance(item)
        if available < used:
            raise ValidationError(
                f"Not enough {item.name}: need {used} {base.code}, have {available}.")

        cost = average_cost(item)  # weighted average, taken before this run's issues
        if issued:
            post_movement(item=item, date=date, movement_type=StockMovement.Type.PRODUCTION_ISSUE,
                          quantity=-issued, unit_cost=cost, source_type="production_run",
                          source_id=run.id, user=user)
        if wasted:
            post_movement(item=item, date=date, movement_type=StockMovement.Type.WASTAGE,
                          quantity=-wasted, unit_cost=cost, source_type="production_run",
                          source_id=run.id, remarks="Damaged / scrap", user=user)
        material_cost += used * cost

        var = variance_pct(used, planned)
        ProductionRunLine.objects.create(
            run=run, item=item, planned_qty=planned, issued_qty=issued,
            wastage_qty=wasted, variance_pct=var, flagged=abs(var) > bom.tolerance_pct)

    post_movement(item=bom.product, date=date, movement_type=StockMovement.Type.PRODUCTION_OUTPUT,
                  quantity=actual_output, source_type="production_run", source_id=run.id,
                  user=user)

    run.material_cost = material_cost.quantize(D("0.01"), ROUND_HALF_UP)
    run.save()
    return run