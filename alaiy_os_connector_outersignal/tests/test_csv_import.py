# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
The customer-export import, without Frappe: python -m unittest tests.test_csv_import

The rows below are made up. The column names are the ones in the platform's
export. Matching and storing are replaced by fakes, so this checks the row
mapping and the counting, not the database.
"""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "outersignal"
PKG = "alaiy_os_connector_outersignal"


def _load(name, filename, **inject):
    spec = importlib.util.spec_from_file_location(f"{PKG}.outersignal.{name}", ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(inject)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ROW = {
    "order_name": "#1042", "email": "Jane@Example.com", "order_email": "jane@example.com",
    "full_name": "Jane Smith", "phone": "+1-555-0100", "age": "34", "gender": "female",
    "city": "Austin", "state": "TX", "country": "US", "property_value": "412000.00",
    "job_title_1": "Nurse", "employer_1": "General Hospital", "job_title_2": "", "employer_2": "",
    "linkedin_url": "https://linkedin.example/jane", "x_url": "", "persona": "The Smart Saver",
    "shopify_customer_id": "8123456789.0", "customer_order_count": "3", "customer_total_spent": "250.50",
}


class TestRow(unittest.TestCase):
    def setUp(self):
        self.parse = _load("parse", "parse.py")

    def test_row_maps_to_the_values_that_are_stored(self):
        d = self.parse.normalize_csv_row(ROW)
        self.assertEqual((d["email"], d["order_name"], d["shopify_customer_id"]),
                         ("jane@example.com", "#1042", "8123456789"))
        self.assertEqual((d["age"], d["gender"], d["job_title"], d["property_value"], d["state"]),
                         (34, "female", "Nurse", 412000.0, "TX"))
        self.assertEqual(d["extra"]["company_name"], "General Hospital")
        self.assertEqual(d["extra"]["social_profiles"], [{"platform": "linkedin", "url": "https://linkedin.example/jane"}])
        self.assertEqual(d["extra"]["total_spent"], 250.5)
        self.assertIsNone(d["researched_at"])

    def test_blank_columns_are_left_out(self):
        d = self.parse.normalize_csv_row(dict(ROW, age="", job_title_1="", property_value=""))
        self.assertIsNone(d["age"])
        self.assertIsNone(d["job_title"])
        self.assertIsNone(d["property_value"])
        self.assertNotIn("other_roles", d["extra"])

    def test_the_order_email_is_used_when_the_email_is_blank(self):
        self.assertEqual(self.parse.normalize_csv_row(dict(ROW, email=""))["email"], "jane@example.com")


class TestImportRows(unittest.TestCase):
    def setUp(self):
        self.stored = []
        calls = self.calls = []

        def find_customer(email, order_name, shopify_customer_id=None):
            calls.append(shopify_customer_id or email)
            if email == "gone@example.com":
                return None, "no customer found for this order name or email"
            if email == "shared@example.com":
                return None, "email matches several customers on email_id"
            return "CUST-" + email, None

        def apply_profile(customer, data):
            if customer == "CUST-boom@example.com":
                raise RuntimeError("write failed")
            self.stored.append(customer)
            return True

        profile = types.SimpleNamespace(find_customer=find_customer, apply_profile=apply_profile)
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

    def rows(self, *emails):
        return [dict(ROW, email=e, shopify_customer_id="") for e in emails]

    def test_counts_and_one_customer_on_several_rows_is_handled_once(self):
        counts = self.module.import_rows(self.rows(
            "a@example.com", "a@example.com", "gone@example.com", "shared@example.com", "boom@example.com"))
        self.assertEqual(counts, {"rows": 5, "customers": 4, "updated": 1, "no_match": 1, "ambiguous": 1, "failed": 1})
        self.assertEqual(self.stored, ["CUST-a@example.com"])
        self.assertEqual(self.calls.count("a@example.com"), 1)

    def test_a_row_with_no_key_is_skipped(self):
        counts = self.module.import_rows([{"age": "30"}])
        self.assertEqual((counts["rows"], counts["customers"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
