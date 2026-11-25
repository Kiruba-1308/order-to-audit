from datetime import date
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from audit.models import AuditLog
from inventory.services import post_movement, stock_balance
from masters.models import Customer, Item
from sales.services import (approve_order, cancel_invoice, create_order,
                            dispatch_invoice, raise_invoice, record_payment)

DAY = date(2026, 11, 4)


class CreditNoteTests(TestCase):
    def setUp(self):
        call_command("seed_benchmark")
        self.murukku = Item.objects.get(name="Murukku 200 g")
        post_movement(item=self.murukku, date=date(2026, 11, 3),
                      movement_type="PRODUCTION_OUTPUT", quantity=188,
                      source_type="production_run", source_id=0)
        self.retailer = Customer.objects.get(name="Retailer A")
        self.salesman = User.objects.get(username="salesman_a")

    def make_invoice(self):
        order = create_order(customer=self.retailer, salesman=self.salesman,
                             lines=[(self.murukku, 150)], date=DAY)
        approve_order(order)
        return raise_invoice(order, date=DAY)

    def test_cancel_dispatched_invoice_returns_stock(self):
        inv = self.make_invoice()
        dispatch_invoice(inv, date=DAY)
        self.assertEqual(stock_balance(self.murukku), D("88"))
        note = cancel_invoice(inv, reason="Wrong price", date=DAY)
        inv.refresh_from_db()
        self.assertEqual(stock_balance(self.murukku), D("238"))
        self.assertEqual(note.total, D("7875.00"))
        self.assertEqual(note.number, "CN/2026-27/0001")
        self.assertTrue(inv.is_cancelled)
        self.assertEqual(inv.outstanding, D("0"))

    def test_cancel_blocked_when_payment_exists(self):
        inv = self.make_invoice()
        record_payment(inv, amount=100, date=DAY)
        with self.assertRaises(ValidationError):
            cancel_invoice(inv, reason="Mistake", date=DAY)

    def test_cannot_cancel_twice(self):
        inv = self.make_invoice()
        cancel_invoice(inv, reason="Duplicate", date=DAY)
        with self.assertRaises(ValidationError):
            cancel_invoice(inv, reason="Again", date=DAY)

    def test_audit_log_records_invoice_events(self):
        inv = self.make_invoice()
        cancel_invoice(inv, reason="Test", date=DAY)
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertIn("CREATE_INVOICE", actions)
        self.assertIn("CANCEL_INVOICE", actions)