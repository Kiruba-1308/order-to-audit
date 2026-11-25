from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def invoice_pdf(invoice):
    """GST tax invoice as PDF bytes. Uses 'Rs.' because the built-in font has no rupee sign."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"Invoice {invoice.number}")
    styles = getSampleStyleSheet()
    fac = settings.FACTORY
    cust = invoice.customer
    story = [
        Paragraph("TAX INVOICE", styles["Title"]),
        Paragraph(f"<b>{fac['name']}</b><br/>GSTIN: {fac['gstin']} &nbsp; State code: {fac['state_code']}",
                  styles["Normal"]),
        Spacer(1, 5 * mm),
        Paragraph(f"<b>Invoice no:</b> {invoice.number} &nbsp;&nbsp; <b>Date:</b> {invoice.date:%d-%m-%Y}",
                  styles["Normal"]),
        Paragraph(f"<b>Bill to:</b> {cust.name}<br/>GSTIN: {cust.gstin or '-'}<br/>"
                  f"Place of supply (state code): {invoice.place_of_supply}", styles["Normal"]),
        Spacer(1, 5 * mm),
    ]

    igst = invoice.is_igst
    head = ["#", "Item", "HSN", "Qty", "Rate", "Taxable"] + (["IGST"] if igst else ["CGST", "SGST"])
    data = [head]
    for n, line in enumerate(invoice.lines.select_related("item"), 1):
        row = [n, line.item.name, line.hsn_code, format(line.quantity.normalize(), "f"),
               f"{line.rate:.2f}", f"{line.taxable_value:.2f}"]
        row += [f"{line.igst:.2f}"] if igst else [f"{line.cgst:.2f}", f"{line.sgst:.2f}"]
        data.append(row)
    rate = invoice.lines.first().gst_rate if invoice.lines.exists() else 0
    tax_cols = ["IGST"] if igst else ["CGST", "SGST"]
    totals = ["", "Total", "", "", "", f"{invoice.taxable_value:.2f}"]
    totals += [f"{invoice.igst:.2f}"] if igst else [f"{invoice.cgst:.2f}", f"{invoice.sgst:.2f}"]
    data.append(totals)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story += [table, Spacer(1, 4 * mm),
              Paragraph(f"GST rate: {rate}% ({' + '.join(tax_cols)})", styles["Normal"]),
              Paragraph(f"<b>Invoice total: Rs. {invoice.total:.2f}</b>", styles["Heading3"]),
              Paragraph(f"Paid: Rs. {invoice.paid:.2f} &nbsp; Outstanding: Rs. {invoice.outstanding:.2f}",
                        styles["Normal"]),
              Spacer(1, 8 * mm),
              Paragraph("This is a computer generated invoice.", styles["Italic"])]
    doc.build(story)
    return buf.getvalue()