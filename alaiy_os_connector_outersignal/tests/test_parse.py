# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Runs without Frappe: python -m unittest tests.test_parse (from this directory).
The webhook payload mirrors the preview the platform renders for the template:
all values are strings, social_profiles and lists are JSON text, and an unfilled
variable comes through as literal braces.
"""

import hashlib
import hmac
import importlib.util
import json
import pathlib
import unittest

_base = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("os_parse", _base / "outersignal" / "parse.py")
parse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse)

PAYLOAD = {
    "event": "segment_entered",
    "research_updated_at": "2026-03-20T17:45:09.123456Z",
    "profile": {
        "name": "Jane Smith",
        "email": "Jane@Example.com",
        "gender": "Female",
        "age": "34",
        "persona": "High-Value Repeat Buyer",
        "city": "San Francisco",
        "state": "California",
        "country": "US",
        "job_title": "Marketing Director",
        "company_name": "Acme Corp",
        "property_value": "750000",
        "education_degree": "",
        "social_profiles": '[{"platform":"instagram","url":"https://instagram.com/janesmith"}]',
        "lists": '["VIP","Contacted"]',
    },
    "order": {"name": "#1042", "email": "{{order.email}}", "count": "12", "total_spent": "2499.50"},
}


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.data = parse.normalize(PAYLOAD)
        self.fields = self.data["fields"]

    def test_strings_become_typed_values(self):
        self.assertEqual(self.data["age"], 34)
        self.assertEqual(self.data["property_value"], 750000.0)
        self.assertEqual(self.fields["customer_order_count"], 12)
        self.assertEqual(self.fields["customer_total_spent"], 2499.5)

    def test_email_is_lowercased_and_order_name_kept(self):
        self.assertEqual(self.data["email"], "jane@example.com")
        self.assertEqual(self.data["order_name"], "#1042")

    def test_blank_and_unrendered_values_are_dropped(self):
        self.assertNotIn("education_degree", self.fields)
        self.assertNotIn("order_email", self.fields)
        self.assertIsNone(parse.normalize({"profile": {"age": "{{profile.age}}"}})["age"])

    def test_webhook_names_map_onto_the_export_columns(self):
        self.assertEqual(self.fields["full_name"], "Jane Smith")
        self.assertEqual(self.fields["job_title_1"], "Marketing Director")
        self.assertEqual(self.fields["employer_1"], "Acme Corp")

    def test_json_text_is_kept_as_text(self):
        self.assertEqual(json.loads(self.fields["lists"]), ["VIP", "Contacted"])
        self.assertEqual(json.loads(self.fields["social_profiles"])[0]["platform"], "instagram")

    def test_timestamp_becomes_naive_utc(self):
        stamp = self.data["researched_at"]
        self.assertEqual((stamp.year, stamp.month, stamp.hour), (2026, 3, 17))
        self.assertIsNone(stamp.tzinfo)

    def test_empty_payload_does_not_raise(self):
        self.assertEqual(parse.normalize({})["email"], "")


class SignatureTest(unittest.TestCase):
    body = b'{"a": 1}'

    def sign(self, secret):
        return hmac.new(secret.encode(), self.body, hashlib.sha256).hexdigest()

    def test_plain_and_prefixed_hex_are_accepted(self):
        digest = self.sign("s3cret")
        self.assertTrue(parse.verify_signature("s3cret", self.body, digest))
        self.assertTrue(parse.verify_signature("s3cret", self.body, "sha256=" + digest))

    def test_wrong_secret_or_body_or_missing_header_is_rejected(self):
        digest = self.sign("s3cret")
        self.assertFalse(parse.verify_signature("other", self.body, digest))
        self.assertFalse(parse.verify_signature("s3cret", b'{"a": 2}', digest))
        self.assertFalse(parse.verify_signature("s3cret", self.body, None))
        self.assertFalse(parse.verify_signature("", self.body, digest))


class CsvRowTest(unittest.TestCase):
    ROW = {
        "order_date": "2026-09-01", "order_name": "#1042", "email": "Jane@Example.com", "order_email": "jane@example.com",
        "channel_name": "Online Store", "full_name": "Jane Smith", "phone": "+1-555-0100", "age": "34",
        "gender": "female", "city": "Austin", "state": "TX", "country": "US", "property_value": "412000.00",
        "job_title_1": "Nurse", "employer_1": "General Hospital", "linkedin_url": "https://linkedin.example/jane",
        "linkedin_followers": "120", "has_vip_alert": "true", "persona": "The Smart Saver",
        "shopify_customer_id": "8123456789.0", "customer_order_count": "3", "customer_total_spent": "250.50",
        "products_purchased": "Ring; Bracelet",
    }

    def test_every_export_column_is_a_stored_field(self):
        d = parse.normalize_csv_row(self.ROW)
        self.assertEqual(d["fields"]["linkedin_followers"], 120)
        self.assertEqual(d["fields"]["has_vip_alert"], 1)
        self.assertEqual(d["fields"]["products_purchased"], "Ring; Bracelet")
        self.assertEqual(d["fields"]["channel_name"], "Online Store")

    def test_row_maps_to_the_values_the_customer_carries(self):
        d = parse.normalize_csv_row(self.ROW)
        self.assertEqual((d["email"], d["order_name"], d["shopify_customer_id"]),
                         ("jane@example.com", "#1042", "8123456789"))
        self.assertEqual((d["age"], d["gender"], d["job_title"], d["property_value"], d["state"]),
                         (34, "female", "Nurse", 412000.0, "TX"))
        self.assertIsNone(d["researched_at"])

    def test_blank_columns_are_left_out(self):
        d = parse.normalize_csv_row(dict(self.ROW, age="", job_title_1="", property_value=""))
        self.assertIsNone(d["age"])
        self.assertIsNone(d["job_title"])
        self.assertIsNone(d["property_value"])
        self.assertNotIn("job_title_1", d["fields"])

    def test_the_order_email_is_used_when_the_email_is_blank(self):
        self.assertEqual(parse.normalize_csv_row(dict(self.ROW, email=""))["email"], "jane@example.com")

    def test_the_stored_columns_cover_the_whole_export(self):
        names = {n for n, _l, _k in parse.PROFILE_COLUMNS}
        header = [
            "order_date", "order_name", "order_email", "channel_name", "customer_number_of_orders", "has_vip_alert",
            "full_name", "email", "phone", "birth_date", "age", "gender", "city", "state", "country", "property_value",
            "biography", "significant_other_name", "relationship_status", "employer_1", "job_title_1", "employer_2",
            "job_title_2", "employer_3", "job_title_3", "education_institution", "education_degree", "linkedin_url",
            "linkedin_followers", "x_url", "x_username", "x_followers", "instagram_url", "instagram_username",
            "instagram_followers", "facebook_url", "facebook_followers", "youtube_url", "youtube_username",
            "youtube_subscribers", "tiktok_url", "tiktok_username", "tiktok_followers", "threads_url",
            "threads_username", "threads_followers", "user_tags", "integration_tags", "system_tags",
            "customer_order_count", "customer_total_spent", "customer_avg_order", "customer_since", "persona",
            "shopify_customer_id", "products_purchased",
        ]
        self.assertEqual(len(header), 56)
        self.assertEqual(set(header) - names, set())


class DoctypeInStepTest(unittest.TestCase):
    def test_the_profile_doctype_has_every_column(self):
        path = _base / "alaiy_os_connector_outersignal" / "doctype" / "outersignal_profile" / "outersignal_profile.json"
        in_doctype = {f["fieldname"] for f in json.loads(path.read_text(encoding="utf-8"))["fields"]}
        missing = {n for n, _l, _k in parse.PROFILE_COLUMNS} - in_doctype
        self.assertEqual(missing, set(), "regenerate the doctype from parse.PROFILE_COLUMNS")


if __name__ == "__main__":
    unittest.main()
