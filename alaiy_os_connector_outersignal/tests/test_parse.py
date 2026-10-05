# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Runs without Frappe: python -m unittest tests.test_parse (from this directory).
The payload below mirrors the preview the platform renders for the template:
all values are strings, social_profiles and lists are JSON text, and an
unfilled variable comes through as literal braces.
"""

import hashlib
import hmac
import importlib.util
import pathlib
import unittest

_path = pathlib.Path(__file__).resolve().parents[1] / "outersignal" / "parse.py"
_spec = importlib.util.spec_from_file_location("os_parse", _path)
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

    def test_strings_become_typed_values(self):
        self.assertEqual(self.data["age"], 34)
        self.assertEqual(self.data["property_value"], 750000.0)
        self.assertEqual(self.data["extra"]["order_count"], 12.0)

    def test_email_is_lowercased_and_order_name_kept(self):
        self.assertEqual(self.data["email"], "jane@example.com")
        self.assertEqual(self.data["order_name"], "#1042")

    def test_blank_and_unrendered_values_are_dropped(self):
        self.assertNotIn("education_degree", self.data["extra"])
        self.assertIsNone(parse.normalize({"profile": {"age": "{{profile.age}}"}})["age"])

    def test_json_text_is_decoded(self):
        self.assertEqual(self.data["extra"]["lists"], ["VIP", "Contacted"])
        self.assertEqual(self.data["extra"]["social_profiles"][0]["platform"], "instagram")

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


if __name__ == "__main__":
    unittest.main()
