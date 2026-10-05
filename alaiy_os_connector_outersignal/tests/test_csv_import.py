# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
The file import's counting, without Frappe: python -m unittest tests.test_csv_import

The rows are made up and keep only the columns the importer reads. Matching and
storing are replaced by a fake, so this checks how rows are folded into people and
how failures are counted, not the database.
"""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "outersignal"
PKG = "alaiy_os_connector_outersignal"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(f"{PKG}.outersignal.{name}", ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestImportRows(unittest.TestCase):
    def setUp(self):
        self.processed = []

        def process(data, source):
            self.processed.append((data["email"] or data["shopify_customer_id"], data["order_name"], source))
            if data["email"] == "boom@example.com":
                raise RuntimeError("write failed")
            if data["email"] == "gone@example.com":
                return "P-gone", set(), 0
            return "P-" + data["email"], {"CUST-" + data["email"]}, 1

        profile = types.SimpleNamespace(
            process=process, profile_key=lambda data: data.get("email") or data.get("shopify_customer_id"))
        frappe = types.ModuleType("frappe")
        frappe.db = types.SimpleNamespace(rollback=lambda: None, commit=lambda: None)
        frappe.log_error = lambda **kwargs: None
        frappe.get_traceback = lambda: "traceback"
        sys.modules["frappe"] = frappe
        pkg = types.ModuleType(PKG)
        pkg.__path__ = []
        sub = types.ModuleType(f"{PKG}.outersignal")
        sub.__path__ = []
        sub.profile = profile
        sub.sync_log = types.SimpleNamespace()
        sys.modules[PKG] = pkg
        sys.modules[f"{PKG}.outersignal"] = sub
        _load("parse", "parse.py")
        self.module = _load("csv_import", "csv_import.py")

    @staticmethod
    def row(email, order, shopify_id=""):
        return {"email": email, "order_name": order, "shopify_customer_id": shopify_id, "age": "30"}

    def test_every_row_is_processed_and_a_person_on_several_orders_counts_once(self):
        counts = self.module.import_rows([
            self.row("a@example.com", "#1"), self.row("a@example.com", "#2"),
            self.row("gone@example.com", "#3"), self.row("b@example.com", "#4"),
        ])
        self.assertEqual(counts, {"rows": 4, "customers": 3, "orders": 4, "linked": 2, "updated": 3, "failed": 0})
        self.assertEqual(len(self.processed), 4)
        self.assertTrue(all(source == "import" for _, _, source in self.processed))

    def test_a_failed_row_is_counted_and_does_not_stop_the_rest(self):
        counts = self.module.import_rows([self.row("boom@example.com", "#1"), self.row("a@example.com", "#2")])
        self.assertEqual((counts["failed"], counts["linked"], counts["customers"]), (1, 1, 2))

    def test_a_row_that_identifies_nobody_is_skipped(self):
        counts = self.module.import_rows([{"age": "30"}])
        self.assertEqual((counts["rows"], counts["customers"], len(self.processed)), (1, 0, 0))

    def test_a_person_with_no_email_is_identified_by_the_shopify_id(self):
        counts = self.module.import_rows([self.row("", "#1", "55"), self.row("", "#2", "55")])
        self.assertEqual((counts["customers"], counts["orders"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
