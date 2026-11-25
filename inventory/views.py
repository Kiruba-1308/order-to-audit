from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Sum
from django.shortcuts import redirect, render

from config.roles import role_required
from masters.models import Item, Supplier, Unit

from .models import StockMovement
from .services import record_purchase
from .summary import parse_range, stock_summary_rows


@role_required("Production", "Admin")
def purchase_new(request):
    suppliers = Supplier.objects.order_by("name")
    items = (Item.objects.filter(kind__in=["RAW", "PACKAGING"], is_active=True)
             .select_related("base_unit").order_by("kind", "name"))
    units = Unit.objects.order_by("code")
    if request.method == "POST":
        try:
            supplier = Supplier.objects.get(pk=request.POST["supplier"])
            item = Item.objects.get(pk=request.POST["item"])
            unit = Unit.objects.get(pk=request.POST["unit"])
            qty = Decimal(request.POST["quantity"])
            rate = Decimal(request.POST["rate"])
            if qty <= 0 or rate < 0:
                raise ValidationError("Quantity must be above zero and rate cannot be negative.")
            record_purchase(supplier=supplier, date=date.today(),
                            invoice_number=request.POST.get("invoice_number", ""),
                            lines=[(item, qty, unit, rate)], user=request.user)
            messages.success(request, f"Purchase saved: {qty} {unit.code} of {item.name}.")
            return redirect("stock_summary")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        except ValueError as e:
            messages.error(request, str(e))
        except (InvalidOperation, KeyError, ObjectDoesNotExist):
            messages.error(request, "Please fill every field with valid values.")
        return redirect("purchase_new")
    return render(request, "purchase_new.html",
                  {"suppliers": suppliers, "items": items, "units": units})


@role_required("Production", "Admin", "Owner", "Auditor")
def stock_summary(request):
    d1, d2 = parse_range(request)
    return render(request, "stock_summary.html",
                  {"rows": stock_summary_rows(d1, d2), "d1": d1, "d2": d2})


@role_required("Production", "Admin", "Owner", "Auditor")
def stock_ledger(request):
    d1, d2 = parse_range(request)
    items = Item.objects.filter(is_active=True).order_by("kind", "name")
    try:
        item = items.get(pk=int(request.GET.get("item", "")))
    except (ValueError, Item.DoesNotExist):
        item = items.first()
    opening = (StockMovement.objects.filter(item=item, date__lt=d1)
               .aggregate(t=Sum("quantity"))["t"] or Decimal("0"))
    running = opening
    rows = []
    moves = (StockMovement.objects.filter(item=item, date__gte=d1, date__lte=d2)
             .select_related("created_by"))
    for m in moves:
        running += m.quantity
        rows.append({"m": m, "balance": running})
    return render(request, "stock_ledger.html",
                  {"items": items, "item": item, "d1": d1, "d2": d2,
                   "opening": opening, "rows": rows, "closing": running})