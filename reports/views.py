import csv
from decimal import Decimal

from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import render

from config.roles import role_required
from inventory.models import PurchaseLine, StockMovement
from inventory.summary import parse_range, stock_summary_rows
from production.models import ProductionRunLine
from sales.models import Invoice, InvoiceLine

ZERO = Decimal("0.00")
REPORT_ROLES = ("Auditor", "Admin", "Owner")


def sales_register(d1, d2):
    header = ["Invoice", "Date", "Customer", "GSTIN", "Place of supply", "Taxable",
              "CGST", "SGST", "IGST", "Total", "Paid", "Outstanding"]
    invoices = (Invoice.objects.filter(date__range=(d1, d2))
                .select_related("customer").order_by("date", "id"))
    rows = [[i.number, i.date, i.customer.name, i.customer.gstin, i.place_of_supply,
             i.taxable_value, i.cgst, i.sgst, i.igst, i.total, i.paid, i.outstanding]
            for i in invoices]
    return header, rows


def sales_by_customer(d1, d2):
    header = ["Customer", "Invoices", "Taxable value", "Total incl. tax"]
    qs = (Invoice.objects.filter(date__range=(d1, d2)).values("customer__name")
          .annotate(n=Sum(1), t=Sum("taxable_value"), g=Sum("total")).order_by("customer__name"))
    return header, [[r["customer__name"], r["n"], r["t"], r["g"]] for r in qs]


def sales_by_product(d1, d2):
    header = ["Product", "Quantity", "Taxable value"]
    qs = (InvoiceLine.objects.filter(invoice__date__range=(d1, d2)).values("item__name")
          .annotate(q=Sum("quantity"), t=Sum("taxable_value")).order_by("item__name"))
    return header, [[r["item__name"], r["q"], r["t"]] for r in qs]


def gst_summary(d1, d2):
    header = ["GST rate %", "Taxable value", "CGST", "SGST", "IGST", "Total tax"]
    qs = (InvoiceLine.objects.filter(invoice__date__range=(d1, d2)).values("gst_rate")
          .annotate(t=Sum("taxable_value"), c=Sum("cgst"), s=Sum("sgst"), i=Sum("igst"))
          .order_by("gst_rate"))
    rows = [[r["gst_rate"], r["t"], r["c"], r["s"], r["i"], r["c"] + r["s"] + r["i"]] for r in qs]
    return header, rows


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


def outstanding(d1, d2):
    header = ["Customer", "Invoice", "Invoice date", "Total", "Paid", "Outstanding",
              "Days", "0-30", "31-60", "61-90", "90+"]
    rows = []
    invoices = Invoice.objects.filter(date__lte=d2).select_related("customer").order_by("customer__name", "date")
    for inv in invoices:
        out = inv.outstanding
        if out <= 0:
            continue
        days = (d2 - inv.date).days
        buckets = [ZERO] * 4
        buckets[0 if days <= 30 else 1 if days <= 60 else 2 if days <= 90 else 3] = out
        rows.append([inv.customer.name, inv.number, inv.date, inv.total, inv.paid, out, days, *buckets])
    return header, rows


REPORTS = {
    "sales_register": ("Sales register", sales_register),
    "sales_by_customer": ("Customer-wise sales", sales_by_customer),
    "sales_by_product": ("Product-wise sales", sales_by_product),
    "gst_summary": ("GST summary (outward supplies)", gst_summary),
    "purchase_register": ("Purchase register", purchase_register),
    "stock_summary": ("Stock summary", stock_summary),
    "stock_ledger": ("Stock ledger", stock_ledger),
    "production_report": ("Production: planned vs actual", production_report),
    "outstanding": ("Outstanding receivables with ageing", outstanding),
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