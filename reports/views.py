import csv
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import render

from config.roles import role_required
from inventory.models import PurchaseLine, StockMovement
from inventory.services import stock_balance
from inventory.summary import parse_range, stock_summary_rows
from masters.models import Item
from production.models import ProductionRun, ProductionRunLine
from sales.models import CreditNote, Invoice, InvoiceLine, Order, Payment

ZERO = Decimal("0.00")
FIELDS = "qtcsi"  # quantity, taxable, cgst, sgst, igst
NIL = {f: ZERO for f in FIELDS}
REPORT_ROLES = ("Auditor", "Admin", "Owner")


# ---------- helpers ----------

def _note(invoice):
    return getattr(invoice, "credit_note", None)


def _group_lines(qs, keys):
    out = {}
    for r in qs.values(*keys).annotate(q=Sum("quantity"), t=Sum("taxable_value"),
                                       c=Sum("cgst"), s=Sum("sgst"), i=Sum("igst")):
        out[tuple(r[k] for k in keys)] = {f: r[f] for f in FIELDS}
    return out


def net_lines(d1, d2, *keys):
    """Invoice lines dated in the range, minus lines of invoices credited in the range."""
    sold = _group_lines(InvoiceLine.objects.filter(invoice__date__range=(d1, d2)), keys)
    back = _group_lines(
        InvoiceLine.objects.filter(invoice__credit_note__date__range=(d1, d2)), keys)
    rows = {}
    for k in sorted(set(sold) | set(back)):
        a, b = sold.get(k, NIL), back.get(k, NIL)
        rows[k] = {f: a[f] - b[f] for f in FIELDS}
    return rows


def _totals(qs):
    a = qs.aggregate(t=Sum("taxable_value"), i=Sum("igst"), c=Sum("cgst"), s=Sum("sgst"))
    return [a["t"] or ZERO, a["i"] or ZERO, a["c"] or ZERO, a["s"] or ZERO]


# ---------- reports: each returns (header, rows) ----------

def sales_register(d1, d2):
    header = ["Invoice", "Date", "Customer", "GSTIN", "Place of supply", "Taxable", "CGST",
              "SGST", "IGST", "Total", "Paid", "Outstanding", "Status", "Credit note"]
    invoices = (Invoice.objects.filter(date__range=(d1, d2))
                .select_related("customer", "credit_note").order_by("date", "id"))
    rows = []
    for i in invoices:
        note = _note(i)
        rows.append([i.number, i.date, i.customer.name, i.customer.gstin, i.place_of_supply,
                     i.taxable_value, i.cgst, i.sgst, i.igst, i.total, i.paid, i.outstanding,
                     "CANCELLED" if i.is_cancelled else "Active", note.number if note else ""])
    return header, rows


def credit_notes(d1, d2):
    """Credit notes in the shape of GSTR-1 table 9B (credit/debit notes to registered persons)."""
    header = ["Recipient GSTIN", "Receiver name", "Credit note", "Date", "Original invoice",
              "Original invoice date", "Note value", "Place of supply", "Taxable value",
              "IGST", "CGST", "SGST", "Reason"]
    notes = (CreditNote.objects.filter(date__range=(d1, d2))
             .select_related("invoice__customer").order_by("date", "id"))
    rows = [[n.invoice.customer.gstin, n.invoice.customer.name, n.number, n.date,
             n.invoice.number, n.invoice.date, n.total, n.invoice.place_of_supply,
             n.taxable_value, n.igst, n.cgst, n.sgst, n.reason] for n in notes]
    return header, rows


def sales_by_customer(d1, d2):
    header = ["Customer", "Invoices", "Credit notes", "Net taxable value", "Net total incl. tax"]
    data = {}
    for r in (Invoice.objects.filter(date__range=(d1, d2)).values("customer__name")
              .annotate(n=Count("id"), t=Sum("taxable_value"), g=Sum("total"))):
        data[r["customer__name"]] = [r["n"], 0, r["t"], r["g"]]
    for r in (CreditNote.objects.filter(date__range=(d1, d2))
              .values("invoice__customer__name")
              .annotate(n=Count("id"), t=Sum("taxable_value"), g=Sum("total"))):
        row = data.setdefault(r["invoice__customer__name"], [0, 0, ZERO, ZERO])
        row[1] = r["n"]
        row[2] -= r["t"]
        row[3] -= r["g"]
    return header, [[name, *vals] for name, vals in sorted(data.items())]


def sales_by_product(d1, d2):
    header = ["Product", "Net quantity", "Net taxable value"]
    rows = net_lines(d1, d2, "item__name")
    return header, [[name, v["q"], v["t"]] for (name,), v in rows.items()]


def gst_summary(d1, d2):
    header = ["GST rate %", "Net taxable value", "CGST", "SGST", "IGST", "Total tax"]
    rows = net_lines(d1, d2, "gst_rate")
    return header, [[rate, v["t"], v["c"], v["s"], v["i"], v["c"] + v["s"] + v["i"]]
                    for (rate,), v in rows.items()]


def gstr1_b2b(d1, d2):
    """GSTR-1 table 4: invoice-wise and rate-wise supplies to registered customers."""
    header = ["Recipient GSTIN", "Receiver name", "Invoice number", "Invoice date",
              "Invoice value", "Place of supply", "Rate %", "Taxable value", "IGST", "CGST",
              "SGST", "Reverse charge", "Credit note issued"]
    invoices = (Invoice.objects.filter(date__range=(d1, d2)).exclude(customer__gstin="")
                .select_related("customer", "credit_note").prefetch_related("lines")
                .order_by("date", "id"))
    rows = []
    for inv in invoices:
        by_rate = {}
        for l in inv.lines.all():
            cur = by_rate.setdefault(l.gst_rate, [ZERO, ZERO, ZERO, ZERO])
            cur[0] += l.taxable_value
            cur[1] += l.igst
            cur[2] += l.cgst
            cur[3] += l.sgst
        note = _note(inv)
        for rate, (t, i, c, s) in sorted(by_rate.items()):
            rows.append([inv.customer.gstin, inv.customer.name, inv.number, inv.date,
                         inv.total, inv.place_of_supply, rate, t, i, c, s, "N",
                         note.number if note else ""])
    return header, rows


def hsn_summary(d1, d2):
    """GSTR-1 table 12: HSN-wise summary of outward supplies, net of credit notes."""
    header = ["HSN", "GST rate %", "Net quantity", "Net taxable value", "IGST", "CGST", "SGST"]
    rows = net_lines(d1, d2, "hsn_code", "gst_rate")
    return header, [[hsn or "-", rate, v["q"], v["t"], v["i"], v["c"], v["s"]]
                    for (hsn, rate), v in rows.items()]


def gstr3b(d1, d2):
    """GSTR-3B table 3.1(a): outward taxable supplies, net of credit notes issued in the period."""
    header = ["3.1(a) Outward taxable supplies", "Taxable value", "IGST", "CGST", "SGST"]
    sold = _totals(Invoice.objects.filter(date__range=(d1, d2)))
    back = _totals(CreditNote.objects.filter(date__range=(d1, d2)))
    net = [a - b for a, b in zip(sold, back)]
    return header, [["Invoices raised", *sold], ["Less: credit notes", *back],
                    ["Net outward supplies", *net]]


def purchase_register(d1, d2):
    header = ["Purchase", "Date", "Supplier", "Supplier invoice", "Item", "Quantity",
              "Unit", "Rate", "Amount"]
    lines = (PurchaseLine.objects.filter(purchase__date__range=(d1, d2))
             .select_related("purchase__supplier", "item", "unit")
             .order_by("purchase__date", "id"))
    rows = [[l.purchase_id, l.purchase.date, l.purchase.supplier.name, l.purchase.invoice_number,
             l.item.name, l.quantity, l.unit.code, l.rate,
             (l.quantity * l.rate).quantize(Decimal("0.01"))] for l in lines]
    return header, rows


def collections(d1, d2):
    header = ["Date", "Customer", "Invoice", "Amount", "Mode", "Reference", "Recorded by"]
    pays = (Payment.objects.filter(date__range=(d1, d2))
            .select_related("invoice__customer", "created_by").order_by("date", "id"))
    rows = [[p.date, p.invoice.customer.name, p.invoice.number, p.amount, p.mode, p.reference,
             p.created_by.username if p.created_by else ""] for p in pays]
    return header, rows


def outstanding(d1, d2):
    header = ["Customer", "Invoice", "Invoice date", "Total", "Paid", "Outstanding",
              "Days", "0-30", "31-60", "61-90", "90+"]
    rows = []
    invoices = (Invoice.objects.filter(date__lte=d2).select_related("customer")
                .order_by("customer__name", "date"))
    for inv in invoices:
        out = inv.outstanding  # cancelled invoices count as zero
        if out <= 0:
            continue
        days = (d2 - inv.date).days
        buckets = [ZERO] * 4
        buckets[0 if days <= 30 else 1 if days <= 60 else 2 if days <= 90 else 3] = out
        rows.append([inv.customer.name, inv.number, inv.date, inv.total, inv.paid, out,
                     days, *buckets])
    return header, rows


def stock_summary(d1, d2):
    header = ["Type", "Item", "Unit", "Opening", "Receipts", "Issues", "Closing",
              "Avg cost", "Value"]
    rows = [[r["kind"], r["item"].name, r["unit"], r["opening"], r["receipts"], r["issues"],
             r["closing"], r["avg_cost"], r["value"]] for r in stock_summary_rows(d1, d2)]
    return header, rows


def stock_ledger(d1, d2):
    header = ["Date", "Item", "Movement", "Quantity", "Unit cost", "Source", "Source id",
              "Remarks", "By"]
    moves = (StockMovement.objects.filter(date__range=(d1, d2))
             .select_related("item", "created_by").order_by("item__name", "date", "id"))
    rows = [[m.date, m.item.name, m.movement_type, m.quantity, m.unit_cost, m.source_type,
             m.source_id, m.remarks, m.created_by.username if m.created_by else ""]
            for m in moves]
    return header, rows


def production_report(d1, d2):
    header = ["Run", "Date", "Product", "Expected output", "Actual output", "Yield variance %",
              "Yield flagged", "Item", "Planned", "Issued", "Wastage", "Actual used",
              "Variance %", "Flagged"]
    lines = (ProductionRunLine.objects.filter(run__date__range=(d1, d2))
             .select_related("run__product", "item").order_by("run__date", "run_id", "id"))
    rows = []
    for l in lines:
        r = l.run
        rows.append([r.id, r.date, r.product.name, r.expected_output, r.actual_output,
                     r.yield_variance_pct, "YES" if r.yield_flagged else "no", l.item.name,
                     l.planned_qty, l.issued_qty, l.wastage_qty, l.actual_qty,
                     l.variance_pct, "YES" if l.flagged else "no"])
    return header, rows


REPORTS = {
    "sales_register": ("Sales register", sales_register),
    "credit_notes": ("Credit notes (GSTR-1 table 9B shape)", credit_notes),
    "sales_by_customer": ("Customer-wise sales (net of credit notes)", sales_by_customer),
    "sales_by_product": ("Product-wise sales (net of credit notes)", sales_by_product),
    "gst_summary": ("GST summary by rate", gst_summary),
    "gstr1_b2b": ("GSTR-1 B2B invoices (table 4 shape)", gstr1_b2b),
    "hsn_summary": ("GSTR-1 HSN summary (table 12 shape)", hsn_summary),
    "gstr3b": ("GSTR-3B outward supplies (table 3.1a shape)", gstr3b),
    "purchase_register": ("Purchase register", purchase_register),
    "collections": ("Payments and collections", collections),
    "outstanding": ("Outstanding receivables with ageing", outstanding),
    "stock_summary": ("Stock summary", stock_summary),
    "stock_ledger": ("Stock ledger", stock_ledger),
    "production_report": ("Production: planned vs actual", production_report),
}


@role_required(*REPORT_ROLES)
def index(request):
    d1, d2 = parse_range(request)
    return render(request, "reports.html", {
        "d1": d1, "d2": d2, "reports": [(k, v[0]) for k, v in REPORTS.items()]})


@role_required(*REPORT_ROLES)
def download(request, name):
    if name not in REPORTS:
        raise Http404
    d1, d2 = parse_range(request)
    header, rows = REPORTS[name][1](d1, d2)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{name}_{d1}_{d2}.csv"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


# ---------- owner dashboard ----------

@role_required(*REPORT_ROLES)
def dashboard(request):
    today = date.today()
    items = (Item.objects.filter(is_active=True).select_related("base_unit")
             .order_by("kind", "name"))
    stock = []
    for item in items:
        bal = stock_balance(item)
        low = item.reorder_level is not None and bal < item.reorder_level
        stock.append({"item": item, "balance": bal, "low": low})

    alerts = []
    for run in ProductionRun.objects.select_related("product").order_by("-id")[:10]:
        bad = [l for l in run.lines.select_related("item") if l.flagged]
        if run.yield_flagged or bad:
            alerts.append({"run": run, "lines": bad})

    costs = []
    for item in items.filter(kind="FINISHED"):
        run = ProductionRun.objects.filter(product=item).order_by("-date", "-id").first()
        if run and run.cost_per_packet is not None:
            price = item.selling_price
            margin = (price - run.cost_per_packet) if price is not None else None
            costs.append({"item": item, "cpp": run.cost_per_packet, "price": price,
                          "margin": margin})

    dues = {}
    for inv in Invoice.objects.filter(cancelled_on__isnull=True).select_related("customer"):
        out = inv.outstanding
        if out > 0:
            dues[inv.customer.name] = dues.get(inv.customer.name, ZERO) + out

    return render(request, "dashboard.html", {
        "today": today,
        "orders_today": Order.objects.filter(date=today).count(),
        "pending_orders": Order.objects.filter(status=Order.Status.SUBMITTED).count(),
        "stock": stock, "low_count": sum(1 for s in stock if s["low"]),
        "alerts": alerts, "costs": costs,
        "dues": sorted(dues.items()), "dues_total": sum(dues.values(), ZERO)})