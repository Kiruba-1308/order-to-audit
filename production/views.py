from datetime import date
from decimal import Decimal, InvalidOperation
from audit.services import log

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from config.roles import role_required
from masters.models import BOM

from . import services
from .models import ProductionRun


def dec(value, default="0"):
    return Decimal((value or "").strip() or default)


def pick_bom(request):
    boms = BOM.objects.filter(is_active=True).select_related("product")
    try:
        return boms.get(pk=int(request.GET.get("bom") or request.POST.get("bom") or ""))
    except (ValueError, BOM.DoesNotExist):
        return boms.first()


@role_required("Production", "Admin", "Owner", "Auditor")
def run_list(request):
    runs = ProductionRun.objects.select_related("product").order_by("-id")
    return render(request, "run_list.html", {"runs": runs})


@role_required("Production", "Admin")
def run_new(request):
    bom = pick_bom(request)
    if bom is None:
        messages.error(request, "No active recipe (BOM) found. Run the seed command.")
        return redirect("home")
    if request.method == "POST":
        try:
            batches = dec(request.POST.get("batches"), "1")
            actual = dec(request.POST.get("actual_output"))
            issues, waste = {}, {}
            for line in bom.lines.select_related("item", "unit"):
                issues[line.item] = dec(request.POST.get(f"issue_{line.item_id}"))
                waste[line.item] = dec(request.POST.get(f"waste_{line.item_id}"))
            labour = dec(request.POST.get("labour"))
            overhead = dec(request.POST.get("overhead"))
            values = [*issues.values(), *waste.values(), actual, labour, overhead]
            if batches <= 0 or any(v < 0 for v in values):
                raise ValidationError("Batches must be above zero; quantities and costs cannot be negative.")
            run = services.post_production_run(
                bom=bom, date=date.today(), actual_output=actual, issues=issues,
                wastage=waste, batches=batches, user=request.user)
            run.labour_cost, run.overhead_cost = labour, overhead
            run.save()
            messages.success(request, f"Production run #{run.id} saved. Stock updated.")
            return redirect("run_detail", pk=run.pk)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        except InvalidOperation:
            messages.error(request, "Please enter valid numbers.")
        return redirect(f"{request.path}?bom={bom.id}")
    return render(request, "run_new.html", {"bom": bom})


@role_required("Production", "Admin", "Owner", "Auditor")
def run_detail(request, pk):
    run = get_object_or_404(ProductionRun.objects.select_related("product", "bom"), pk=pk)
    cpp = run.cost_per_packet
    price = run.product.selling_price
    margin = (price - cpp) if (cpp is not None and price is not None) else None
    margin_pct = (margin / price * 100).quantize(Decimal("0.1")) if (margin is not None and price) else None
    return render(request, "run_detail.html", {
        "run": run, "lines": run.lines.select_related("item__base_unit"),
        "cpp": cpp, "margin": margin, "margin_pct": margin_pct})


@role_required("Production", "Admin")
def run_costs(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if request.method == "POST":
        try:
            labour = dec(request.POST.get("labour"))
            overhead = dec(request.POST.get("overhead"))
            if labour < 0 or overhead < 0:
                raise ValidationError("Costs cannot be negative.")
            run.labour_cost, run.overhead_cost = labour, overhead
            run.save()
            messages.success(request, "Costs saved.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        except InvalidOperation:
            messages.error(request, "Please enter valid numbers.")
    return redirect("run_detail", pk=pk)

@role_required("Production", "Admin")
def run_costs(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if request.method == "POST":
        try:
            labour = dec(request.POST.get("labour"))
            overhead = dec(request.POST.get("overhead"))
            if labour < 0 or overhead < 0:
                raise ValidationError("Costs cannot be negative.")
            changed = (run.labour_cost, run.overhead_cost) != (labour, overhead)
            detail = (f"labour {run.labour_cost}->{labour}, "
                      f"gas/power {run.overhead_cost}->{overhead}")
            run.labour_cost, run.overhead_cost = labour, overhead
            run.save()
            if changed:
                log(request.user, "EDIT_RUN_COSTS", run, detail)
            messages.success(request, "Costs saved.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        except InvalidOperation:
            messages.error(request, "Please enter valid numbers.")
    return redirect("run_detail", pk=pk)