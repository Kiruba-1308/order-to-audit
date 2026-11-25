from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from config.roles import role_required
from inventory.services import stock_balance
from masters.models import Customer, Item

from . import services
from .models import Order


@login_required
def home(request):
    return render(request, "home.html")


@role_required("Salesman", "Admin")
def order_new(request):
    customers = Customer.objects.order_by("name")
    items = Item.objects.filter(kind="FINISHED", is_active=True,
                                selling_price__isnull=False).order_by("name")
    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=request.POST.get("customer"))
        lines = []
        for item in items:
            raw = request.POST.get(f"qty_{item.id}", "").strip()
            if not raw:
                continue
            try:
                qty = Decimal(raw)
            except InvalidOperation:
                messages.error(request, f"Invalid quantity for {item.name}.")
                return redirect("order_new")
            if qty > 0:
                lines.append((item, qty))
        if not lines:
            messages.error(request, "Add a quantity for at least one product.")
            return redirect("order_new")
        order = services.create_order(customer=customer, salesman=request.user,
                                      lines=lines, date=date.today(),
                                      notes=request.POST.get("notes", ""))
        messages.success(request, f"Order #{order.id} submitted to the factory.")
        return redirect("my_orders")
    return render(request, "order_new.html", {"customers": customers, "items": items})


@role_required("Salesman", "Admin")
def my_orders(request):
    orders = (Order.objects.filter(salesman=request.user)
              .select_related("customer").prefetch_related("lines").order_by("-id"))
    totals = {}
    for o in orders:
        if o.status != Order.Status.REJECTED:
            totals[o.customer.name] = totals.get(o.customer.name, Decimal("0")) + o.total_value
    return render(request, "my_orders.html",
                  {"orders": orders, "by_customer": sorted(totals.items())})


@role_required("Admin")
def admin_orders(request):
    orders = (Order.objects.select_related("customer", "salesman")
              .prefetch_related("lines").order_by("-id"))
    status = request.GET.get("status")
    if status:
        orders = orders.filter(status=status)
    return render(request, "admin_orders.html",
                  {"orders": orders, "statuses": Order.Status.values})


@role_required("Admin")
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "salesman"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        today = date.today()
        try:
            if action == "update" and order.status == Order.Status.SUBMITTED:
                new_values = []
                for line in order.lines.all():
                    qty = Decimal(request.POST[f"qty_{line.id}"])
                    rate = Decimal(request.POST[f"rate_{line.id}"])
                    if qty <= 0 or rate < 0:
                        raise ValidationError("Quantity must be above zero and rate cannot be negative.")
                    new_values.append((line, qty, rate))
                for line, qty, rate in new_values:
                    line.quantity, line.rate = qty, rate
                    line.save()
                messages.success(request, "Order updated.")
            elif action == "approve":
                services.approve_order(order, user=request.user)
                messages.success(request, "Order approved.")
            elif action == "reject":
                services.reject_order(order, user=request.user)
                messages.success(request, "Order rejected.")
            elif action == "invoice":
                invoice = services.raise_invoice(order, date=today, user=request.user)
                messages.success(request, f"Invoice {invoice.number} raised.")
            elif action in ("dispatch", "payment"):
                invoice = order.invoices.first()
                if invoice is None:
                    raise ValidationError("Raise the invoice first.")
                if action == "dispatch":
                    services.dispatch_invoice(invoice, date=today, user=request.user)
                    messages.success(request, "Dispatch recorded. Stock reduced.")
                else:
                    services.record_payment(
                        invoice, amount=Decimal(request.POST["amount"]), date=today,
                        mode=request.POST.get("mode", "CASH"),
                        reference=request.POST.get("reference", ""), user=request.user)
                    messages.success(request, "Payment recorded.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        except (InvalidOperation, KeyError):
            messages.error(request, "Please enter valid numbers.")
        return redirect("order_detail", pk=pk)

    rows = []
    for line in order.lines.select_related("item"):
        available = stock_balance(line.item)
        rows.append({"line": line, "available": available,
                     "shortage": max(line.quantity - available, Decimal("0"))})
    return render(request, "order_detail.html",
                  {"order": order, "rows": rows, "invoices": order.invoices.all()})