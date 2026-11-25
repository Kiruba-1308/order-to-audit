from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import StockMovement
from inventory.services import post_movement
from masters.models import BOM, BOMLine, Customer, Item, Supplier, Unit

ROLES = ["Salesman", "Admin", "Production", "Auditor", "Owner"]
USERS = [  # username, role
    ("salesman_a", "Salesman"),
    ("salesman_b", "Salesman"),
    ("admin1", "Admin"),
    ("prod1", "Production"),
    ("auditor1", "Auditor"),
    ("owner1", "Owner"),
]
PASSWORD = "demo1234"  # test logins for evaluators; listed in the README


class Command(BaseCommand):
    help = "Load Section 5 benchmark master data (safe to run twice)."

    @transaction.atomic
    def handle(self, *args, **opts):
        # Roles and users
        for r in ROLES:
            Group.objects.get_or_create(name=r)
        for username, role in USERS:
            u, created = User.objects.get_or_create(username=username)
            if created:
                u.set_password(PASSWORD)
                u.save()
            u.groups.set([Group.objects.get(name=role)])

        # Login for the Django admin (master data screens)
        root, created = User.objects.get_or_create(
            username="superadmin", defaults=dict(is_staff=True, is_superuser=True))
        if created:
            root.set_password(PASSWORD)
            root.save()

        # Units
        U = {}
        for code, name, dim, to_base in [
            ("kg", "Kilogram", "WEIGHT", "1"),
            ("g", "Gram", "WEIGHT", "0.001"),
            ("l", "Litre", "VOLUME", "1"),
            ("ml", "Millilitre", "VOLUME", "0.001"),
            ("pc", "Piece", "COUNT", "1"),
            ("pkt", "Packet", "COUNT", "1"),
        ]:
            U[code], _ = Unit.objects.get_or_create(
                code=code, defaults=dict(name=name, dimension=dim, to_base=D(to_base)))

        # Items
        def item(name, kind, unit, **kw):
            return Item.objects.get_or_create(
                name=name, defaults=dict(kind=kind, base_unit=U[unit], **kw))[0]

        flour = item("Flour", "RAW", "kg")
        oil = item("Cooking oil", "RAW", "l")
        spice = item("Salt and spice mix", "RAW", "kg")
        pouch = item("200 g pouch", "PACKAGING", "pc")
        carton = item("Carton (20 packets)", "PACKAGING", "pc")
        murukku = item("Murukku 200 g", "FINISHED", "pkt", hsn_code="2106",
                       gst_rate=D("5"), selling_price=D("50"), packets_per_carton=20)

        # Reorder levels (used by the low-stock alerts on the owner dashboard)
        for name, level in [("Flour", 50), ("Cooking oil", 20), ("Salt and spice mix", 2),
                            ("200 g pouch", 400), ("Carton (20 packets)", 15),
                            ("Murukku 200 g", 100)]:
            Item.objects.filter(name=name).update(reorder_level=D(str(level)))

        # Opening stock (finished goods have no unit cost: an assumption for the README)
        for it, qty, cost in [(flour, 100, 42), (oil, 30, 140), (spice, 5, 200),
                              (pouch, 500, "2.50"), (carton, 30, 15), (murukku, 50, None)]:
            if not StockMovement.objects.filter(item=it, movement_type="OPENING").exists():
                post_movement(item=it, date=date(2026, 11, 1), movement_type="OPENING",
                              quantity=qty, unit_cost=None if cost is None else D(str(cost)),
                              source_type="opening", remarks="Opening balance")

        # Recipe (BOM) for one batch
        if not BOM.objects.filter(product=murukku).exists():
            bom = BOM.objects.create(product=murukku, name="Murukku 200 g standard batch",
                                     expected_yield=D("200"), tolerance_pct=D("3"))
            for it, qty, unit in [(flour, 40, "kg"), (oil, 10, "l"), (spice, "1.2", "kg"),
                                  (pouch, 200, "pc"), (carton, 10, "pc")]:
                BOMLine.objects.create(bom=bom, item=it, quantity=D(str(qty)), unit=U[unit])

        # Customers
        Customer.objects.get_or_create(name="Retailer A", defaults=dict(
            kind="RETAILER", state_code="33", gstin="33AAAAA0000A1Z5"))      # Tamil Nadu
        Customer.objects.get_or_create(name="Distributor B", defaults=dict(
            kind="DISTRIBUTOR", state_code="29", gstin="29AAAAA0000A1Z5"))   # Karnataka

        # Supplier
        Supplier.objects.get_or_create(name="Demo Flour Traders")

        self.stdout.write(self.style.SUCCESS("Benchmark master data loaded."))