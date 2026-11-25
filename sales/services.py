from decimal import ROUND_HALF_UP
from decimal import Decimal as D

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from audit.services import log
from inventory.models import StockMovement
from inventory.services import post_movement, stock_balance

from .models import CreditNote, Invoice, InvoiceLine, Order, OrderLine, Payment

TWO = D("0.01")
ZERO = D("0.00")


def money(x):
    return D(x).quantize(TWO, ROUND_HALF_UP)


def financial_year(d):
    """Indian financial year runs April to March: 4 Nov 2026 -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def gst_split(taxable, rate, intra_state):
    """Returns (cgst, sgst, igst). Intra-state splits tax in half; inter-state is all IGST."""
    tax = money(taxable * D(rate) / 100)
    if intra_state:
        cgst = money(tax / 2)
        return cgst, tax - cgst, ZERO
    return ZERO, ZERO, tax


@transaction.atomic
def create_order(*, customer, salesman, lines, date, notes=""):
    """lines = [(item, quantity), ...]. The price comes from the item's price list."""
    order = Order.objects.create(customer=customer, salesman=salesman, date=date, notes=notes)
    for item, qty in lines:
        OrderLine.objects.create(order=order, item=item, quantity=D(str(qty)),
                                 rate=item.selling_price)
    log(salesman, "CREATE_ORDER", order, f"{len(lines)} line(s) for {customer.name}")
    return order


def stock_check(order):
    """Does finished-goods stock cover the order? One row per line."""
    rows = []
    for line in order.lines.select_related("item"):
        available = stock_balance(line.item)
        rows.append({"item": line.item, "ordered": line.quantity, "available": available,
                     "shortage": max(line.quantity - available, D("0"))})
    return rows


@transaction.atomic
def approve_order(order, user=None):
    if order.status != Order.Status.SUBMITTED:
        raise ValidationError("Only submitted orders can be approved.")
    short = [r for r in stock_check(order) if r["shortage"] > 0]
    if short:
        raise ValidationError("Insufficient stock: " + "; ".join(
            f"{r['item'].name} short by {r['shortage']}" for r in short))
    order.status = Order.Status.APPROVED
    order.approved_by = user
    order.save()
    log(user, "APPROVE_ORDER", order)


def reject_order(order, user=None):
    if order.status != Order.Status.SUBMITTED:
        raise ValidationError("Only submitted orders can be rejected.")
    order.status = Order.Status.REJECTED
    order.approved_by = user
    order.save()
    log(user, "REJECT_ORDER", order)


@transaction.atomic
def raise_invoice(order, *, date, user=None):
    if order.status != Order.Status.APPROVED:
        raise ValidationError("Only approved orders can be invoiced.")
    customer = order.customer
    intra = customer.state_code == settings.FACTORY["state_code"]
    fy = financial_year(date)
    seq = Invoice.objects.filter(fy=fy).count() + 1  # invoices are never deleted
    invoice = Invoice.objects.create(
        number=f"{fy}/{seq:04d}", fy=fy, order=order, customer=customer, date=date,
        place_of_supply=customer.state_code, is_igst=not intra, created_by=user)

    taxable_t = cgst_t = sgst_t = igst_t = ZERO
    for line in order.lines.select_related("item"):
        taxable = money(line.quantity * line.rate)
        cgst, sgst, igst = gst_split(taxable, line.item.gst_rate, intra)
        InvoiceLine.objects.create(
            invoice=invoice, item=line.item, hsn_code=line.item.hsn_code,
            quantity=line.quantity, rate=line.rate, gst_rate=line.item.gst_rate,
            taxable_value=taxable, cgst=cgst, sgst=sgst, igst=igst)
        taxable_t += taxable
        cgst_t += cgst
        sgst_t += sgst
        igst_t += igst

    invoice.taxable_value = taxable_t
    invoice.cgst, invoice.sgst, invoice.igst = cgst_t, sgst_t, igst_t
    invoice.total = taxable_t + cgst_t + sgst_t + igst_t
    invoice.save()
    order.status = Order.Status.INVOICED
    order.save()
    log(user, "CREATE_INVOICE", invoice, f"Total {invoice.total} for {customer.name}")
    return invoice


@transaction.atomic
def dispatch_invoice(invoice, *, date, user=None):
    if invoice.cancelled_on:
        raise ValidationError("A cancelled invoice cannot be dispatched.")
    if invoice.dispatched_on:
        raise ValidationError("This invoice is already dispatched.")
    lines = list(invoice.lines.select_related("item"))
    for line in lines:
        available = stock_balance(line.item)
        if available < line.quantity:
            raise ValidationError(
                f"Not enough {line.item.name}: need {line.quantity}, have {available}.")
    for line in lines:
        post_movement(item=line.item, date=date, movement_type=StockMovement.Type.DISPATCH,
                      quantity=-line.quantity, source_type="invoice",
                      source_id=invoice.id, user=user)
    invoice.dispatched_on = date
    invoice.save()
    invoice.order.status = Order.Status.DISPATCHED
    invoice.order.save()
    log(user, "DISPATCH", invoice, f"Dispatched on {date}")


@transaction.atomic
def record_payment(invoice, *, amount, date, mode="CASH", reference="", user=None):
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Payment must be more than zero.")
    if amount > invoice.outstanding:
        raise ValidationError("Payment is more than the outstanding amount.")
    payment = Payment.objects.create(invoice=invoice, date=date, amount=amount, mode=mode,
                                     reference=reference, created_by=user)
    log(user, "PAYMENT", invoice, f"Received {amount} by {mode}")
    return payment


@transaction.atomic
def cancel_invoice(invoice, *, reason, date, user=None):
    """Cancel a posted invoice with a credit note. If it was dispatched, the goods are
    taken back into finished-goods stock. Invoices with payments must be settled first."""
    if invoice.cancelled_on:
        raise ValidationError("This invoice is already cancelled.")
    if not reason.strip():
        raise ValidationError("Enter a reason for the credit note.")
    if invoice.payments.exists():
        raise ValidationError("This invoice has payments recorded. Settle them before cancelling.")

    fy = financial_year(date)
    seq = CreditNote.objects.filter(fy=fy).count() + 1
    note = CreditNote.objects.create(
        number=f"CN/{fy}/{seq:04d}", fy=fy, invoice=invoice, date=date, reason=reason.strip(),
        taxable_value=invoice.taxable_value, cgst=invoice.cgst, sgst=invoice.sgst,
        igst=invoice.igst, total=invoice.total, created_by=user)

    if invoice.dispatched_on:
        for line in invoice.lines.select_related("item"):
            post_movement(item=line.item, date=date,
                          movement_type=StockMovement.Type.SALES_RETURN,
                          quantity=line.quantity, source_type="credit_note",
                          source_id=note.id, remarks=f"Credit note {note.number}", user=user)

    invoice.cancelled_on = date
    invoice.save()
    invoice.order.status = Order.Status.CANCELLED
    invoice.order.save()
    log(user, "CANCEL_INVOICE", invoice, f"Credit note {note.number}: {reason.strip()}")
    return note


def customer_outstanding(customer):
    return sum((i.outstanding for i in Invoice.objects.filter(customer=customer)), ZERO)