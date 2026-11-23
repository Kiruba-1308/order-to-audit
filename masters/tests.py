from decimal import Decimal as D

from django.core.management import call_command
from django.test import TestCase

from inventory.models import StockMovement
from inventory.services import stock_balance
from masters.models import Item, Unit
from masters.units import convert


class SeedAndLedgerTests(TestCase):
    def setUp(self):
        call_command("seed_benchmark")

    def test_opening_balances(self):
        expected = {"Flour": 100, "Cooking oil": 30, "Salt and spice mix": 5,
                    "200 g pouch": 500, "Carton (20 packets)": 30, "Murukku 200 g": 50}
        for name, qty in expected.items():
            self.assertEqual(stock_balance(Item.objects.get(name=name)), D(qty))

    def test_seed_is_idempotent(self):
        call_command("seed_benchmark")
        self.assertEqual(stock_balance(Item.objects.get(name="Flour")), D("100"))

    def test_ledger_rows_are_immutable(self):
        m = StockMovement.objects.first()
        m.quantity = D("999")
        with self.assertRaises(PermissionError):
            m.save()
        with self.assertRaises(PermissionError):
            m.delete()

    def test_unit_conversion(self):
        kg, g = Unit.objects.get(code="kg"), Unit.objects.get(code="g")
        self.assertEqual(convert(D("1500"), g, kg), D("1.5"))
        self.assertEqual(convert(D("2"), kg, g), D("2000"))
        with self.assertRaises(ValueError):
            convert(1, kg, Unit.objects.get(code="l"))