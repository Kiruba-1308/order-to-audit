# Order-to-Audit: small food manufacturer prototype

Prototype for the NIT Tiruchirappalli (Centre for Digital Infrastructure) winter internship task.
One system that takes a snack factory from a salesman's order to the monthly auditor's reports.

- **Demo video:** [paste unlisted YouTube or Drive link]
- **Repository:** https://github.com/Kiruba-1308/order-to-audit
- **Design note:** see [DESIGN.md](DESIGN.md) (data model, stock and BOM logic, costing)

## Stack and why

Django 5.2 (Python), SQLite for the demo (a PostgreSQL switch is included), server-rendered mobile-friendly pages, ReportLab for invoice PDFs.
Django provides login, groups, migrations, an ORM and exact `Decimal` arithmetic with little code, so the time went into the business logic (ledger, BOM, GST) rather than plumbing. All money and quantities use `Decimal`, never floats.

## Run it locally (single command)

Windows: `run.bat`  Mac/Linux: `./run.sh`

The script creates a virtual environment, installs packages, migrates the database, loads the Section 5 data (`seed_benchmark`, safe to run twice) and starts the server at http://127.0.0.1:8000.

Manual steps:

```
python -m venv .venv
.venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_benchmark
python manage.py runserver
```

Run the tests with `python manage.py test` (28 tests).
A `Dockerfile` and `docker-compose.yml` (PostgreSQL + web) are included but were **not tested** on my machine; use the script if Docker gives any trouble.

## Test logins (password for all: `demo1234`)

| Role | Username | Can do |
|---|---|---|
| Salesman | `salesman_a`, `salesman_b` | Take orders on mobile, see own orders and customer-wise sales |
| Factory admin | `admin1` | Approve orders, GST invoices, dispatch, payments, credit notes |
| Production supervisor | `prod1` | Purchases, production runs, stock pages |
| Accountant / auditor | `auditor1` | Read-only reports (CSV), stock, audit trail |
| Owner | `owner1` | Dashboard, reports, audit trail |
| Master data (Django admin) | `superadmin` | Items, customers, suppliers, BOMs at `/admin/` |

Each role sees only its own screens; other pages return 403 Forbidden.

## What is built (against the Section 6 tiers)

**Must have:** login with 5 roles; product, customer, supplier, raw-material and BOM masters (Django admin); mobile-friendly order entry and admin approval; GST invoice as PDF; production run that updates raw-material and finished-goods stock automatically; planned vs actual consumption and yield with variance; stock summary and stock ledger; sales register and stock report as CSV.

**Should have:** purchases and supplier records; payments, outstanding and ageing; cost per packet with overheads and margin; GST summary; variance flags beyond a tolerance; owner dashboard.

**Also built:** audit trail of edits and actions (user and time); credit-note cancellation of invoices (no deletion); low-stock alerts via reorder levels; GSTR-1 shaped reports (B2B invoices, HSN summary, credit notes) and a GSTR-3B 3.1(a) summary; WhatsApp share link for invoices.

**Reports** (date range, CSV that opens in Excel): sales register, credit notes, customer-wise and product-wise sales, GST summary, GSTR-1 B2B, HSN summary, GSTR-3B outward supplies, purchase register, payments and collections, outstanding with ageing, stock summary, stock ledger, production planned vs actual. Sales and GST reports are net of credit notes.

## Design in brief (details in DESIGN.md)

- **Stock is an append-only ledger** (`StockMovement`); balances are the sum of movements and cannot be overwritten. Every movement links to its source document.
- **Production runs** run in one transaction: stock is checked, materials issued per BOM line, finished goods added, variance computed per line and for yield. A short stock rejects the whole run.
- **Sales loop:** order, admin edit and approve (blocked on shortage), GST invoice, dispatch (reduces stock), payments (cannot exceed outstanding), credit note to cancel.
- **GST:** CGST + SGST when the customer's state code equals the factory's (33, Tamil Nadu), otherwise IGST. Invoice numbers are `FY/sequence`, e.g. `2026-27/0001`.

## Costing method

- **Material cost: weighted average**, replayed from the ledger. Flour: (100 x 42 + 60 x 45) / 160 = Rs 43.125/kg.
- **Overheads:** labour and gas/power entered per run are charged to that run's product (single-product runs). Cost per packet = (materials + labour + overheads) / good packets. Damaged pouches are consumed stock, so their cost is included.

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
| Distributor B | Shortage of 32; IGST if invoiced | Shortage of 32 shown, approval blocked; IGST 5% on invoice |
| Cost per packet | own figure | **Rs 31.14** (5,855 / 188), margin Rs 18.86 (37.7%) |

**Differences worth noting.** The 200 g pouch shows -3.00% (194 used vs 200 planned) and is not flagged because the tolerance is "beyond 3%". Cartons show -10% (9 used vs 10 in the BOM) and are flagged; the brief does not list this check, so it is an extra finding rather than an error. With FIFO instead of weighted average, the run's flour would cost 1,680 instead of 1,725 and cost per packet would be about Rs 30.90.

## Assumptions

- HSN code 2106 and GST 5% for packaged snacks (the brief fixes 5% for this exercise).
- Factory and customer GSTINs are dummy values; the factory is in Tamil Nadu (state code 33), Distributor B in Karnataka (29).
- Opening finished goods carry no unit cost.
- Transactions are dated with today's date.
- Prices come from the item's selling price (no customer-specific prices).
- Invoice PDFs print "Rs." because the built-in PDF font has no rupee sign.

## Known gaps

Not built: offline order capture with sync; batch and expiry tracking; partial dispatch and returns (a credit note reverses the whole invoice); refunds for paid invoices (an invoice with payments cannot be cancelled); production planning from pending orders; route and GPS visit log; Tally export; e-invoice / e-way bill format; Tamil interface; hosted demo link; edits to posted invoices are not allowed (cancel and re-issue instead).