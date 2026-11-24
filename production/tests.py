from datetime import date
from decimal import Decimal as D

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from inventory.services import average_cost, record_purchase, stock_balance
from masters.models import BOM, Item, Supplier, Unit
from production.models import ProductionRun
from production.services import post_production_run


class BenchmarkProductionTests(TestCase):
    def setUp(self):
        call_command("seed_benchmark")
        kg = Unit.objects.get(code="kg")
        # Benchmark step 1: purchase 60 kg flour at Rs 45/kg
        record_purchase(supplier=Supplier.objects.get(name="Demo Flour Traders"),
                        date=date(2026, 11, 2), invoice_number="P-1",
                        lines=[(self.it("Flour"), D("60"), kg, D("45"))])

    def it(self, name):
        return Item.objects.get(name=name)

    def run_benchmark(self):
        bom = BOM.objects.get(product=self.it("Murukku 200 g"))
        return post_production_run(
            bom=bom, date=date(2026, 11, 3), actual_output=188,
            issues={self.it("Flour"): 40, self.it("Cooking oil"): "10.5",
                    self.it("Salt and spice mix"): "1.2",
                    self.it("200 g pouch"): 188, self.it("Carton (20 packets)"): 9},
            wastage={self.it("200 g pouch"): 6})

    def test_purchase_updates_stock_and_average_cost(self):
        self.assertEqual(stock_balance(self.it("Flour")), D("160"))
        self.assertEqual(average_cost(self.it("Flour")), D("43.1250"))

    def test_closing_balances(self):
        self.run_benchmark()
        self.assertEqual(stock_balance(self.it("Flour")), D("120"))
        self.assertEqual(stock_balance(self.it("Cooking oil")), D("19.5"))
        self.assertEqual(stock_balance(self.it("200 g pouch")), D("306"))
        self.assertEqual(stock_balance(self.it("Carton (20 packets)")), D("21"))
        self.assertEqual(stock_balance(self.it("Murukku 200 g")), D("238"))

    def test_variances_are_flagged(self):
        run = self.run_benchmark()
        self.assertEqual(run.yield_variance_pct, D("-6.00"))
        self.assertTrue(run.yield_flagged)
        oil = run.lines.get(item=self.it("Cooking oil"))
        self.assertEqual(oil.variance_pct, D("5.00"))
        self.assertTrue(oil.flagged)
        flour = run.lines.get(item=self.it("Flour"))
        self.assertEqual(flour.variance_pct, D("0.00"))
        self.assertFalse(flour.flagged)

    def test_cost_per_packet(self):
        run = self.run_benchmark()
        self.assertEqual(run.material_cost, D("4055.00"))
        run.labour_cost = D("1200")
        run.overhead_cost = D("600")
        run.save()
        self.assertEqual(run.cost_per_packet, D("31.14"))

    def test_insufficient_stock_saves_nothing(self):
        bom = BOM.objects.get(product=self.it("Murukku 200 g"))
        with self.assertRaises(ValidationError):
            post_production_run(bom=bom, date=date(2026, 11, 3), actual_output=0,
                                issues={self.it("Flour"): 500})
        self.assertEqual(stock_balance(self.it("Flour")), D("160"))
        self.assertEqual(ProductionRun.objects.count(), 0)