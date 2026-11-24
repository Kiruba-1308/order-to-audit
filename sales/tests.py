from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from inventory.services import post_movement, stock_balance
from masters.models import Customer, Item
from sales.services import (approve_order, create_order, customer_outstanding,
                            dispatch_invoice, financial_year, gst_split,
                            raise_invoice, record_payment, stock_check)

DAY = date(2026, 11, 4)


class SalesBenchmarkTests(TestCase):
    def setUp(self):
        call_command("seed_benchmark")
        self.murukku = Item.objects.get(name="Murukku 200 g")
        # Shortcut for the production run: 188 good packets, so 50 + 188 = 238 in stock
        post_movement(item=self.murukku, date=date(2026, 11, 3),
                      movement_type="PRODUCTION_OUTPUT", quantity=188,
                      source_type="production_run", source_id=0)
        self.salesman_a = User.objects.get(username="salesman_a")
        self.salesman_b = User.objects.get(username="salesman_b")
        self.retailer_a = Customer.objects.get(name="Retailer A")
        self.distributor_b = Customer.objects.get(name="Distributor B")

    def invoice_for_retailer_a(self):
        order = create_order(customer=self.retailer_a, salesman=self.salesman_a,
                             lines=[(self.murukku, 150)], date=DAY)
        approve_order(order)
        return raise_invoice(order, date=DAY)

    def test_retailer_a_invoice_amounts(self):
        inv = self.invoice_for_retailer_a()
        self.assertEqual(inv.number, "2026-27/0001")
        self.assertEqual(inv.taxable_value, D("7500.00"))
        self.assertEqual(inv.cgst, D("187.50"))
        self.assertEqual(inv.sgst, D("187.50"))
        self.assertEqual(inv.igst, D("0"))
        self.assertEqual(inv.total, D("7875.00"))
        self.assertFalse(inv.is_igst)

    def test_dispatch_reduces_finished_goods(self):
        self.assertEqual(stock_balance(self.murukku), D("238"))
        inv = self.invoice_for_retailer_a()
        dispatch_invoice(inv, date=DAY)
        self.assertEqual(stock_balance(self.murukku), D("88"))

    def test_payment_and_outstanding(self):
        inv = self.invoice_for_retailer_a()
        record_payment(inv, amount=4000, date=DAY)
        inv.refresh_from_db()
        self.assertEqual(inv.outstanding, D("3875.00"))
        self.assertEqual(customer_outstanding(self.retailer_a), D("3875.00"))

    def test_overpayment_is_rejected(self):
        inv = self.invoice_for_retailer_a()
        with self.assertRaises(ValidationError):
            record_payment(inv, amount=9000, date=DAY)

    def test_distributor_b_shortage_blocks_approval(self):
        dispatch_invoice(self.invoice_for_retailer_a(), date=DAY)  # leaves 88
        order_b = create_order(customer=self.distributor_b, salesman=self.salesman_b,
                               lines=[(self.murukku, 120)], date=DAY)
        rows = stock_check(order_b)
        self.assertEqual(rows[0]["available"], D("88"))
        self.assertEqual(rows[0]["shortage"], D("32"))
        with self.assertRaises(ValidationError):
            approve_order(order_b)

    def test_igst_applies_for_other_state(self):
        self.assertEqual(gst_split(D("6000.00"), D("5"), False),
                         (D("0"), D("0"), D("300.00")))
        order = create_order(customer=self.distributor_b, salesman=self.salesman_b,
                             lines=[(self.murukku, 10)], date=DAY)
        approve_order(order)
        inv = raise_invoice(order, date=DAY)
        self.assertTrue(inv.is_igst)
        self.assertEqual(inv.igst, D("25.00"))
        self.assertEqual(inv.cgst, D("0"))

    def test_financial_year_numbering(self):
        self.assertEqual(financial_year(date(2027, 3, 31)), "2026-27")
        self.assertEqual(financial_year(date(2027, 4, 1)), "2027-28")