from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from inventory.services import post_movement
from masters.models import Customer, Item
from reports.views import gstr1_b2b, gstr3b, sales_by_customer
from sales.services import approve_order, cancel_invoice, create_order, raise_invoice

DAY = date(2026, 11, 4)
RANGE = (date(2026, 11, 1), date(2026, 11, 30))


class ReportTests(TestCase):
    def setUp(self):
        call_command("seed_benchmark")
        self.murukku = Item.objects.get(name="Murukku 200 g")
        post_movement(item=self.murukku, date=date(2026, 11, 3),
                      movement_type="PRODUCTION_OUTPUT", quantity=188,
                      source_type="production_run", source_id=0)

    def make_invoice(self):
        order = create_order(customer=Customer.objects.get(name="Retailer A"),
                             salesman=User.objects.get(username="salesman_a"),
                             lines=[(self.murukku, 150)], date=DAY)
        approve_order(order)
        return raise_invoice(order, date=DAY)

    def test_gstr3b_is_net_of_credit_notes(self):
        inv = self.make_invoice()
        _, rows = gstr3b(*RANGE)
        net = rows[2]
        self.assertEqual(net[1], D("7500.00"))
        self.assertEqual(net[3], D("187.50"))
        self.assertEqual(net[4], D("187.50"))
        cancel_invoice(inv, reason="Test", date=DAY)
        _, rows = gstr3b(*RANGE)
        self.assertEqual(rows[2][1], D("0.00"))

    def test_b2b_lists_invoice_by_rate(self):
        self.make_invoice()
        _, rows = gstr1_b2b(*RANGE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "2026-27/0001")
        self.assertEqual(rows[0][7], D("7500.00"))

    def test_customer_sales_net_of_credit_notes(self):
        inv = self.make_invoice()
        cancel_invoice(inv, reason="Test", date=DAY)
        _, rows = sales_by_customer(*RANGE)
        self.assertEqual(rows[0][3], D("0.00"))