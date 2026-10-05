# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Storing, merging and matching profiles, without Frappe:
    python -m unittest tests.test_profile_store

The database is a small fake, so this checks what is written and how repeat orders
are folded together, not the SQL.
"""

import datetime
import importlib.util
import pathlib
import sys
import types
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1] / "outersignal"
PKG = "alaiy_os_connector_outersignal"


class FakeDB:
    def __init__(self):
        self.profiles = {}   # name -> dict
        self.orders = []     # (parent, order_name)
        self.links = []      # (parent, customer)
        self.customers = {}  # name -> dict of osg values
        self.counter = 0

    # -- reads
    def _record(self, name, fields):
        row = self.profiles[name]
        record = types.SimpleNamespace(**{f: row.get(f) for f in (fields or []) if f != "name"})
        record.name = name
        record.get = lambda key, default=None: row.get(key, default)
        return record

    def get_value(self, doctype, filters, fields=None, as_dict=False):
        if doctype == "Customer":
            return self.customers.get(filters, {}).get(fields)
        if isinstance(filters, dict):
            for name, row in self.profiles.items():
                if row.get("profile_key") == filters.get("profile_key"):
                    return self._record(name, fields)
            return None
        return self._record(filters, fields) if filters in self.profiles else None

    def exists(self, doctype, filters):
        if doctype == "OuterSignal Profile Order":
            return (filters["parent"], filters["order_name"]) in self.orders
        return (filters["parent"], filters["customer"]) in self.links

    def count(self, doctype, filters):
        pool = self.orders if doctype == "OuterSignal Profile Order" else self.links
        return len([1 for p, _ in pool if p == filters["parent"]])

    # -- writes
    def set_value(self, doctype, name, values, *args, **kwargs):
        if doctype == "Customer":
            self.customers.setdefault(name, {}).update(values)
        else:
            self.profiles[name].update(values)


def load():
    frappe = types.ModuleType("frappe")
    db = frappe.db = FakeDB()
    frappe.meta_fields = set()

    class Doc(dict):
        def insert(self, **kwargs):
            if self["doctype"] == "OuterSignal Profile":
                db.counter += 1
                self.name = f"P{db.counter}"
                db.profiles[self.name] = {k: v for k, v in self.items() if k != "doctype"}
            elif self["doctype"] == "OuterSignal Profile Order":
                db.orders.append((self["parent"], self["order_name"]))
            else:
                db.links.append((self["parent"], self["customer"]))

    frappe.get_doc = lambda values: Doc(values)
    frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda f: False)
    frappe.get_all = lambda doctype, filters=None, **kw: [o for p, o in db.orders if p == filters["parent"]]
    sys.modules["frappe"] = frappe
    pkg = types.ModuleType(PKG)
    pkg.__path__ = []
    sub = types.ModuleType(f"{PKG}.outersignal")
    sub.__path__ = []
    sys.modules[PKG] = pkg
    sys.modules[f"{PKG}.outersignal"] = sub
    for name in ("parse", "profile"):
        spec = importlib.util.spec_from_file_location(f"{PKG}.outersignal.{name}", BASE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        setattr(sub, name, module)
    return sub.profile, sub.parse, frappe


def row(**over):
    base = {"order_date": "2026-09-01", "order_name": "#1", "email": "jane@example.com", "age": "34",
            "gender": "female", "city": "Austin", "state": "TX", "country": "US", "property_value": "400000",
            "job_title_1": "Nurse", "persona": "Saver", "shopify_customer_id": "55",
            "customer_order_count": "1", "customer_total_spent": "100"}
    base.update(over)
    return base


class TestApplyProfile(unittest.TestCase):
    def test_a_missing_age_or_home_value_is_written_as_zero_not_null(self):
        """osg_age and osg_property_value cannot hold NULL; None failed 324 rows of the first import."""
        profile, parse, frappe = load()
        data = parse.normalize_csv_row(row(age="", property_value=""))
        profile.apply_profile("CUST-1", data)
        written = frappe.db.customers["CUST-1"]
        self.assertEqual((written["osg_age"], written["osg_property_value"]), (0, 0))

    def test_long_text_is_cut_to_the_customer_columns(self):
        profile, parse, frappe = load()
        profile.apply_profile("CUST-1", parse.normalize_csv_row(row(job_title_1="x" * 400)))
        self.assertEqual(len(frappe.db.customers["CUST-1"]["osg_job_title"]), 140)


class TestMerge(unittest.TestCase):
    def test_counters_keep_the_largest_value_and_blanks_never_erase(self):
        profile, _, _ = load()
        merged = profile.merge_fields(
            {"customer_order_count": 3, "city": "Austin", "customer_total_spent": 900.0},
            {"customer_order_count": 2, "city": None, "customer_total_spent": 100.0}, True)
        self.assertEqual((merged["customer_order_count"], merged["city"], merged["customer_total_spent"]), (3, "Austin", 900.0))

    def test_an_older_row_fills_gaps_but_does_not_replace_values(self):
        profile, _, _ = load()
        merged = profile.merge_fields({"city": "Austin", "gender": None}, {"city": "Dallas", "gender": "female"}, False)
        self.assertEqual((merged["city"], merged["gender"]), ("Austin", "female"))

    def test_a_newer_row_replaces_values(self):
        profile, _, _ = load()
        self.assertEqual(profile.merge_fields({"city": "Austin"}, {"city": "Dallas"}, True)["city"], "Dallas")


class TestStoreProfile(unittest.TestCase):
    def test_a_profile_is_kept_even_with_no_customer(self):
        profile, parse, frappe = load()
        name = profile.store_profile(parse.normalize_csv_row(row()), "import")
        self.assertEqual(frappe.db.profiles[name]["profile_key"], "jane@example.com")
        self.assertEqual(frappe.db.profiles[name]["source"], "import")
        self.assertEqual(frappe.db.links, [])

    def test_the_same_person_on_several_orders_is_one_record_with_every_order(self):
        profile, parse, frappe = load()
        first = profile.store_profile(parse.normalize_csv_row(row(order_name="#1", order_date="2026-09-01")), "import")
        second = profile.store_profile(parse.normalize_csv_row(
            row(order_name="#2", order_date="2026-09-20", customer_order_count="2", customer_total_spent="260")), "import")
        self.assertEqual(first, second)
        self.assertEqual(len(frappe.db.profiles), 1)
        self.assertEqual(sorted(o for _, o in frappe.db.orders), ["#1", "#2"])
        self.assertEqual(frappe.db.profiles[first]["customer_order_count"], 2)
        self.assertEqual(frappe.db.profiles[first]["customer_total_spent"], 260)

    def test_running_the_same_file_again_adds_nothing(self):
        profile, parse, frappe = load()
        for _ in range(2):
            profile.store_profile(parse.normalize_csv_row(row()), "import")
        self.assertEqual(len(frappe.db.profiles), 1)
        self.assertEqual(len(frappe.db.orders), 1)

    def test_a_row_without_a_number_does_not_lower_a_stored_one(self):
        profile, parse, frappe = load()
        profile.store_profile(parse.normalize_csv_row(row(customer_order_count="5")), "import")
        name = profile.store_profile(parse.normalize_csv_row(row(order_name="#2", customer_order_count="")), "import")
        self.assertEqual(frappe.db.profiles[name]["customer_order_count"], 5)

    def test_an_older_dated_delivery_leaves_the_profile_but_records_the_order(self):
        profile, parse, frappe = load()
        newer = parse.normalize(
            {"research_updated_at": "2026-06-01T00:00:00Z", "profile": {"email": "jane@example.com", "city": "Dallas"},
             "order": {"name": "#9"}})
        profile.store_profile(newer, "webhook")
        older = parse.normalize(
            {"research_updated_at": "2026-01-01T00:00:00Z", "profile": {"email": "jane@example.com", "city": "Houston"},
             "order": {"name": "#3"}})
        name = profile.store_profile(older, "webhook")
        self.assertEqual(frappe.db.profiles[name]["city"], "Dallas")
        self.assertEqual(sorted(o for _, o in frappe.db.orders), ["#3", "#9"])

    def test_the_shopify_id_identifies_a_row_with_no_email(self):
        profile, parse, frappe = load()
        name = profile.store_profile(parse.normalize_csv_row(row(email="", order_email="")), "import")
        self.assertEqual(frappe.db.profiles[name]["profile_key"], "55")

    def test_a_row_that_identifies_nobody_is_not_stored(self):
        profile, parse, frappe = load()
        data = parse.normalize_csv_row(row(email="", order_email="", shopify_customer_id=""))
        self.assertIsNone(profile.store_profile(data, "import"))
        self.assertEqual(frappe.db.profiles, {})


class TestSeveralCustomerRecords(unittest.TestCase):
    def test_every_customer_the_person_is_found_under_gets_the_profile(self):
        """Alaiy OS may hold one Customer per order for the same person."""
        profile, parse, frappe = load()
        by_order = {"#1": "CUST-A", "#2": "CUST-B"}
        profile.find_customer = lambda email, order_name, sid=None: (by_order.get(order_name), None)
        profile.process(parse.normalize_csv_row(row(order_name="#1")), "import")
        name, customers, updated = profile.process(parse.normalize_csv_row(row(order_name="#2")), "import")
        self.assertEqual(customers, {"CUST-A", "CUST-B"})
        self.assertEqual(updated, 2)
        self.assertEqual(sorted(c for _, c in frappe.db.links), ["CUST-A", "CUST-B"])
        self.assertEqual(frappe.db.customers["CUST-B"]["osg_gender"], "female")

    def test_a_person_nobody_matches_is_still_kept(self):
        profile, parse, frappe = load()
        profile.find_customer = lambda email, order_name, sid=None: (None, "no customer found")
        name, customers, updated = profile.process(parse.normalize_csv_row(row()), "import")
        self.assertTrue(name)
        self.assertEqual((customers, updated), (set(), 0))


if __name__ == "__main__":
    unittest.main()
