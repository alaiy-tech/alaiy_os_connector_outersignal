# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Pure helpers for the inbound enrichment webhook: signature check and payload
normalisation. No Frappe imports, so they run in a plain unit test.

Every value in the delivered JSON is a string (numbers included), a variable the
platform could not fill comes through as the literal "{{...}}" text, and the
list-valued fields arrive as JSON encoded inside a string. normalize() undoes
all three.
"""

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

SIGNATURE_HEADER = "X-Signature-256"

_UNRENDERED = re.compile(r"^\s*\{\{.*\}\}\s*$")


def verify_signature(secret, body, header_value):
    """HMAC-SHA256 of the raw body, hex encoded, optionally prefixed with sha256=."""
    if not secret or not header_value:
        return False
    given = header_value.strip()
    if given.lower().startswith("sha256="):
        given = given[7:]
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given.lower())


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or _UNRENDERED.match(value):
            return None
    return value


def _number(value):
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value)))
    except ValueError:
        return None


def _json_value(value):
    value = _clean(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _datetime(value):
    value = _clean(value)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def normalize(payload):
    """Flatten one delivery into the values stored on the Customer."""
    profile = payload.get("profile") or {}
    order = payload.get("order") or {}

    age = _number(profile.get("age"))
    extra = {
        "name": _clean(profile.get("name")),
        "phone": _clean(profile.get("phone")),
        "birth_date": _clean(profile.get("birth_date")),
        "relationship_status": _clean(profile.get("relationship_status")),
        "biography": _clean(profile.get("biography")),
        "company_name": _clean(profile.get("company_name")),
        "education_institution": _clean(profile.get("education_institution")),
        "education_degree": _clean(profile.get("education_degree")),
        "social_profiles": _json_value(profile.get("social_profiles")),
        "lists": _json_value(profile.get("lists")),
        "order_count": _number(order.get("count")),
        "total_spent": _number(order.get("total_spent")),
        "avg_value": _number(order.get("avg_value")),
    }
    return {
        "email": (_clean(profile.get("email")) or "").lower(),
        "order_name": _clean(order.get("name")),
        "researched_at": _datetime(payload.get("research_updated_at")),
        "age": int(round(age)) if age is not None else None,
        "gender": _clean(profile.get("gender")),
        "persona": _clean(profile.get("persona")),
        "job_title": _clean(profile.get("job_title")),
        "property_value": _number(profile.get("property_value")),
        "city": _clean(profile.get("city")),
        "state": _clean(profile.get("state")),
        "country": _clean(profile.get("country")),
        "extra": {k: v for k, v in extra.items() if v is not None},
    }


_SOCIAL_NETWORKS = ("linkedin", "x", "instagram", "facebook", "youtube", "tiktok", "threads")


def _shopify_id(value):
    value = _clean(value)
    if value is None:
        return None
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def normalize_csv_row(row):
    """One row of the platform's customer export, in the shape normalize()
    returns plus the Shopify customer id the row carries. The export has no
    research date, so researched_at is None and never blocks a later webhook."""
    def get(key):
        return _clean(row.get(key))

    age = _number(get("age"))
    socials = [
        {"platform": network, "url": get(f"{network}_url")}
        for network in _SOCIAL_NETWORKS if get(f"{network}_url")
    ]
    other_roles = [
        {"title": get(f"job_title_{i}"), "employer": get(f"employer_{i}")}
        for i in (2, 3) if get(f"job_title_{i}") or get(f"employer_{i}")
    ]
    extra = {
        "name": get("full_name"),
        "phone": get("phone"),
        "birth_date": get("birth_date"),
        "relationship_status": get("relationship_status"),
        "biography": get("biography"),
        "company_name": get("employer_1"),
        "other_roles": other_roles or None,
        "education_institution": get("education_institution"),
        "education_degree": get("education_degree"),
        "social_profiles": socials or None,
        "order_count": _number(get("customer_order_count")),
        "total_spent": _number(get("customer_total_spent")),
        "avg_value": _number(get("customer_avg_order")),
        "customer_since": get("customer_since"),
    }
    return {
        "email": (get("email") or get("order_email") or "").lower(),
        "order_name": get("order_name"),
        "shopify_customer_id": _shopify_id(row.get("shopify_customer_id")),
        "researched_at": None,
        "age": int(round(age)) if age is not None else None,
        "gender": get("gender"),
        "persona": get("persona"),
        "job_title": get("job_title_1"),
        "property_value": _number(get("property_value")),
        "city": get("city"),
        "state": get("state"),
        "country": get("country"),
        "extra": {k: v for k, v in extra.items() if v is not None},
    }
