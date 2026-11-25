# Order-to-Audit: small food manufacturer prototype

Prototype for the NIT Tiruchirappalli (Centre for Digital Infrastructure) winter internship task.
One system that takes a snack factory from a salesman's order to the monthly auditor's reports.

**Demo video:** [paste link]
**Repository:** [paste GitHub link]

## Stack and why

Django 5.2 (Python), SQLite for the demo (PostgreSQL-ready), server-rendered mobile-friendly pages, ReportLab for PDF.
Django gives login, groups, migrations, an ORM and exact `Decimal` arithmetic with very little code, so time went into the business logic (ledger, BOM, GST) rather than plumbing. All money and quantities use `Decimal`, never floats.

## Run it locally

```
python -m venv .venv
.venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_benchmark
python manage.py runserver
```

Open http://127.0.0.1:8000. `seed_benchmark` loads the Section 5 master data and opening stock, and is safe to run twice.
Run the tests with `python manage.py test` (21 tests, covering stock, BOM variance, costing, GST and invoice numbering).

## Test logins (password for all: `demo1234`)

| Role | Username |
|---|---|
| Salesman | `salesman_a`, `salesman_b` |
| Factory admin | `admin1` |
| Production supervisor | `prod1` |
| Accountant / auditor | `auditor1` |
| Owner | `owner1` |

Each role sees only its own screens. Other pages return 403 Forbidden.

## What is built (against the Section 6 tiers)

**Must have:** login with 5 roles; product, customer, supplier, raw-material and BOM masters (Django admin); mobile-friendly order entry and admin approval; GST invoice as PDF; production run that updates raw-material and finished-goods stock automatically; planned vs actual consumption and yield with variance; stock summary and stock ledger; sales register and stock report as CSV.

**Should have:** purchases and supplier records; payments, outstanding and ageing; cost per packet with overheads; GST summary report; variance flags beyond a tolerance; weighted-average costing.

## Design in brief

- **Stock is a ledger.** Every change is an append-only `StockMovement` row (item, signed quantity in the item's base unit, unit cost, source document type and id, user, time). Balances are always the sum of the ledger and are never typed in. Rows cannot be edited or deleted in code or in the admin.
- **Traceability.** Each movement links to its source: opening, purchase, production run, or invoice dispatch.
- **Units.** Each unit stores a factor to its dimension's base unit (kg, litre, piece). Purchases and BOM lines can use g, kg, ml, l, etc., and are converted when posted. Cartons are a packaging item counted in pieces; finished goods are counted in packets.
- **Production run.** One transaction: it checks stock, posts issue and wastage movements per BOM line, posts the finished-goods output, and stores planned vs actual figures per line. If any material is short, nothing is saved.
- **Variance** = (actual − planned) / planned x 100, flagged when beyond the BOM's tolerance (3%). Actual consumption = issued + wastage.
- **Sales loop.** Order, admin edit/approve (blocked on stock shortage), GST invoice, dispatch (reduces stock), payments (cannot exceed outstanding).
- **GST.** CGST + SGST when the customer's state code equals the factory's (33, Tamil Nadu); otherwise IGST. Tax is rounded to paise and CGST + SGST always add up to the full tax. Invoice numbers are `FY/sequence`, e.g. `2026-27/0001`, with the financial year starting in April.

## Costing method

- **Material cost: weighted average.** The average is replayed from the ledger (receipts at their cost raise the average; issues leave it unchanged). Chosen because it is simple to explain and audit and smooths price changes. Flour: (100 x 42 + 60 x 45) / 160 = Rs 43.125/kg.
- **Overheads:** labour and gas/power entered per run are charged entirely to that run's product (single-product factory). Cost per packet = (materials + labour + overheads) / actual good packets. Damaged pouches are consumed stock, so their cost is included.
- **Valuation of finished goods** in the stock summary uses the latest run's cost per packet.

## Benchmark results (Section 5)

| Check | Expected | Result |
|---|---|---|
| Flour closing | 120 kg | 120 kg |
| Oil closing | 19.5 L | 19.5 L |
| Pouches closing | 306 | 306 |
| Finished goods after run | 238 | 238 |
| After Retailer A dispatch | 88 | 88 |
| Yield variance | -6%, flagged | -6.00%, flagged |
| Oil variance | +5%, flagged | +5.00%, flagged |
| Retailer A invoice | 7,500 + 187.50 + 187.50 = 7,875 | 7,875.00 |
| Retailer A outstanding | 3,875 | 3,875.00 |
| Distributor B | Shortage of 32; IGST if invoiced | Shortage of 32 shown; approval blocked; IGST 5% on invoice |
| Cost per packet | own figure | **Rs 31.14** (materials 4,055 + labour 1,200 + gas/power 600 = 5,855 / 188), margin Rs 18.86 (37.7%) |

**Differences worth noting.** The 200 g pouch shows -3.00% variance (194 used vs 200 planned) and is not flagged because the tolerance is "beyond 3%". Cartons show -10% (9 used vs 10 in the BOM) and are flagged; the brief does not list this check, so it is an extra finding, not an error. With FIFO instead of weighted average, flour for the run would cost 1,680 instead of 1,725 and cost per packet would be about Rs 30.90.

## Assumptions

- HSN code 2106 and GST 5% for packaged snacks (the brief fixes 5% for this exercise).
- Factory GSTIN and customer GSTINs are dummy values; the factory is in Tamil Nadu (state code 33), Distributor B in Karnataka (29).
- Opening finished goods carry no unit cost.
- Transactions are dated with today's date.
- Invoice PDFs print "Rs." because the built-in PDF font has no rupee sign.
- Prices come from the item's selling price (no customer-specific prices).

## Known gaps

Not built yet: credit-note cancellation of invoices; audit log of edits to invoices and production runs; offline order capture; Docker Compose (run locally with the steps above); batch and expiry tracking; partial dispatch and returns; owner dashboard; GSTR-1/3B-shaped export (the GST summary is by rate only); Tamil interface; hosted demo link.