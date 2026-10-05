# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Pure helpers for the inbound enrichment data: signature check and normalisation of
a webhook delivery or a row of the customer export. No Frappe imports, so they run in
a plain unit test.

Every value in a delivered JSON is a string (numbers included), a variable the
platform could not fill comes through as the literal "{{...}}" text, and the
list-valued fields arrive as JSON encoded inside a string. The normalisers undo all
three, and both produce the same `fields` dict, keyed by the export's column names,
which is what the OuterSignal Profile record stores.
"""

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

SIGNATURE_HEADER = "X-Signature-256"

_UNRENDERED = re.compile(r"^\s*\{\{.*\}\}\s*$")

# Every column of the platform's customer export, in its order, with how each is
# stored. "check" is a yes/no flag, "int" and "float" cannot hold NULL in the
# database (an unknown value is stored as 0), "text" is long free text and "data"
# is a short string. Dates are kept as the text the export gives.
PROFILE_COLUMNS = [
    ("order_date", "Order Date", "data"),
    ("order_name", "Order Name", "data"),
    ("order_email", "Order Email", "data"),
    ("channel_name", "Channel Name", "data"),
    ("customer_number_of_orders", "Customer Number Of Orders", "int"),
    ("has_vip_alert", "Has VIP Alert", "check"),
    ("full_name", "Full Name", "data"),
    ("email", "Email", "data"),
    ("phone", "Phone", "data"),
    ("birth_date", "Birth Date", "data"),
    ("age", "Age", "int"),
    ("gender", "Gender", "data"),
    ("city", "City", "data"),
    ("state", "State", "data"),
    ("country", "Country", "data"),
    ("property_value", "Property Value", "float"),
    ("biography", "Biography", "text"),
    ("significant_other_name", "Significant Other Name", "data"),
    ("relationship_status", "Relationship Status", "data"),
    ("employer_1", "Employer 1", "data"),
    ("job_title_1", "Job Title 1", "data"),
    ("employer_2", "Employer 2", "data"),
    ("job_title_2", "Job Title 2", "data"),
    ("employer_3", "Employer 3", "data"),
    ("job_title_3", "Job Title 3", "data"),
    ("education_institution", "Education Institution", "data"),
    ("education_degree", "Education Degree", "data"),
    ("linkedin_url", "LinkedIn URL", "data"),
    ("linkedin_followers", "LinkedIn Followers", "int"),
    ("x_url", "X URL", "data"),
    ("x_username", "X Username", "data"),
    ("x_followers", "X Followers", "int"),
    ("instagram_url", "Instagram URL", "data"),
    ("instagram_username", "Instagram Username", "data"),
    ("instagram_followers", "Instagram Followers", "int"),
    ("facebook_url", "Facebook URL", "data"),
    ("facebook_followers", "Facebook Followers", "int"),
    ("youtube_url", "YouTube URL", "data"),
    ("youtube_username", "YouTube Username", "data"),
    ("youtube_subscribers", "YouTube Subscribers", "int"),
    ("tiktok_url", "TikTok URL", "data"),
    ("tiktok_username", "TikTok Username", "data"),
    ("tiktok_followers", "TikTok Followers", "int"),
    ("threads_url", "Threads URL", "data"),
    ("threads_username", "Threads Username", "data"),
    ("threads_followers", "Threads Followers", "int"),
    ("user_tags", "User Tags", "text"),
    ("integration_tags", "Integration Tags", "text"),
    ("system_tags", "System Tags", "text"),
    ("customer_order_count", "Customer Order Count", "int"),
    ("customer_total_spent", "Customer Total Spent", "float"),
    ("customer_avg_order", "Customer Avg Order", "float"),
    ("customer_since", "Customer Since", "data"),
    ("persona", "Persona", "data"),
    ("shopify_customer_id", "Shopify Customer ID", "data"),
    ("products_purchased", "Products Purchased", "text"),
    # Delivered by the webhook only.
    ("lists", "Lists", "text"),
    ("social_profiles", "Social Profiles", "text"),
]

COLUMN_KINDS = {name: kind for name, _label, kind in PROFILE_COLUMNS}


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


def _shopify_id(value):
    value = _clean(value)
    if value is None:
        return None
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _typed(name, value):
    """The value of one column, cleaned and converted to what the field holds."""
    kind = COLUMN_KINDS.get(name, "data")
    value = _clean(value)
    if kind in ("int", "float"):
        number = _number(value)
        if number is None:
            return None
        return int(round(number)) if kind == "int" else number
    if kind == "check":
        return 1 if str(value or "").strip().lower() in ("1", "true", "yes", "y") else 0
    if name == "shopify_customer_id":
        return _shopify_id(value)
    if name == "email" and value is not None:
        return str(value).lower()
    return value


def _json_text(value):
    value = _json_value(value)
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _result(fields, researched_at):
    """The common shape: the values the Customer carries, the full `fields`, and an
    `extra` dict with everything the profile has, kept on the Customer as JSON."""
    fields = {k: v for k, v in fields.items() if v is not None}
    age = fields.get("age")
    return {
        "email": fields.get("email") or (fields.get("order_email") or "").lower(),
        "order_name": fields.get("order_name"),
        "shopify_customer_id": fields.get("shopify_customer_id"),
        "researched_at": researched_at,
        "age": age or None,
        "gender": fields.get("gender"),
        "persona": fields.get("persona"),
        "job_title": fields.get("job_title_1"),
        "property_value": fields.get("property_value") or None,
        "city": fields.get("city"),
        "state": fields.get("state"),
        "country": fields.get("country"),
        "fields": fields,
        "extra": {k: v for k, v in fields.items() if v not in (None, "", 0)},
    }


def normalize(payload):
    """One webhook delivery."""
    profile = payload.get("profile") or {}
    order = payload.get("order") or {}
    mapped = {
        "full_name": profile.get("name"), "email": profile.get("email"), "phone": profile.get("phone"),
        "birth_date": profile.get("birth_date"), "age": profile.get("age"), "gender": profile.get("gender"),
        "relationship_status": profile.get("relationship_status"), "persona": profile.get("persona"),
        "biography": profile.get("biography"), "city": profile.get("city"), "state": profile.get("state"),
        "country": profile.get("country"), "job_title_1": profile.get("job_title"),
        "employer_1": profile.get("company_name"),
        "education_institution": profile.get("education_institution"),
        "education_degree": profile.get("education_degree"), "property_value": profile.get("property_value"),
        "order_name": order.get("name"), "order_email": order.get("email"),
        "customer_order_count": order.get("count"), "customer_total_spent": order.get("total_spent"),
        "customer_avg_order": order.get("avg_value"),
    }
    fields = {name: _typed(name, value) for name, value in mapped.items()}
    fields["social_profiles"] = _json_text(profile.get("social_profiles"))
    fields["lists"] = _json_text(profile.get("lists"))
    return _result(fields, _datetime(payload.get("research_updated_at")))


def normalize_csv_row(row):
    """One row of the platform's customer export. The export has no research date, so
    researched_at is None and never blocks a later, dated delivery."""
    fields = {name: _typed(name, row.get(name)) for name, _label, _kind in PROFILE_COLUMNS
              if name not in ("lists", "social_profiles")}
    return _result(fields, None)
