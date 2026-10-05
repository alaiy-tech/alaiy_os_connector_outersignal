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
