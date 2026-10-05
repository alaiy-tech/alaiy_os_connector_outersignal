# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Match an enrichment delivery (or a row of the customer export) to Customers, keep
it as an OuterSignal Profile, and copy it onto the Customers.

One person can appear many times: on several rows of the export (one per order),
in several deliveries (one per new order), and as several Customer records here
(Alaiy OS may have created one per order). The profile is therefore one record per
person, every order is listed on it, and the profile is copied onto every Customer
the person is found under.

An order name such as "#1042" is only unique inside one store, so it can point at
several Customers; the email narrows that down, and when it cannot, that order
links nothing rather than a guess.
"""

import json

import frappe

from alaiy_os_connector_outersignal.outersignal.parse import COLUMN_KINDS

PROFILE = "OuterSignal Profile"
PROFILE_ORDER = "OuterSignal Profile Order"
PROFILE_CUSTOMER = "OuterSignal Profile Customer"

FIELD_MAP = {
    "age": "osg_age",
    "gender": "osg_gender",
    "persona": "osg_persona",
    "job_title": "osg_job_title",
    "property_value": "osg_property_value",
    "city": "osg_city",
    "state": "osg_state",
    "country": "osg_country",
}
# Numeric columns cannot hold NULL, so a value the profile lacks is stored as 0,
# which the reports treat as "not known".
NUMERIC_COLUMNS = ("osg_age", "osg_property_value")
# Customer fields are short Data columns.
_TEXT_LIMIT = 140

# Counters that only grow: the largest value seen is the current one.
CUMULATIVE = ("customer_number_of_orders", "customer_order_count", "customer_total_spent")
_EMPTY = (None, "", 0)


def find_customer(email, order_name, shopify_customer_id=None):
    """Return (customer, None) on a single match, else (None, reason).

    The Shopify customer id is the surest key when a row carries one. It is only
    unique inside one store, so more than one match falls through to the order
    name and the email like any other row."""
    if shopify_customer_id and frappe.get_meta("Customer").has_field("sh_shopify_customer_id"):
        found = frappe.get_all(
            "Customer", filters={"sh_shopify_customer_id": str(shopify_customer_id)}, pluck="name", limit=2
        )
        if len(found) == 1:
            return found[0], None

    if order_name and frappe.get_meta("Sales Order").has_field("sh_shopify_order_name"):
        bare = order_name.lstrip("#")
        rows = frappe.get_all(
            "Sales Order",
            filters={
                "sh_shopify_order_name": ["in", [order_name, bare, "#" + bare]],
                "docstatus": ["<", 2],
            },
            fields=["customer", "contact_email"],
            limit=100,
        )
        customers = {r.customer for r in rows}
        if len(customers) == 1:
            return customers.pop(), None
        if len(customers) > 1:
            narrowed = {r.customer for r in rows if (r.contact_email or "").lower() == email}
            if email and len(narrowed) == 1:
                return narrowed.pop(), None
            return None, "order name is shared by several customers and the email did not narrow it"

    if email:
        for field in ("osg_email", "email_id"):
            found = frappe.get_all("Customer", filters={field: email}, pluck="name", limit=2)
            if len(found) == 1:
                return found[0], None
            if len(found) > 1:
                return None, f"email matches several customers on {field}"
    return None, "no customer found for this order name or email"


def find_customers(email, order_names, shopify_customer_id=None):
    """Every Customer record this person can be found under, as a set.

    Looked up by the Shopify id and email first, then by each order they placed, since
    Alaiy OS may hold a separate Customer per order."""
    found = set()
    customer, _ = find_customer(email, None, shopify_customer_id)
    if customer:
        found.add(customer)
    for order_name in order_names:
        customer, _ = find_customer(email, order_name, None)
        if customer:
            found.add(customer)
    return found


def apply_profile(customer, data):
    """Write the enrichment values onto a Customer. Returns False when a newer profile is stored."""
    stored = frappe.db.get_value("Customer", customer, "osg_research_updated_at")
    if stored and data["researched_at"] and data["researched_at"] < stored:
        return False

    values = {column: data[key] for key, column in FIELD_MAP.items()}
    for column in NUMERIC_COLUMNS:
        values[column] = values[column] or 0
    for column, value in values.items():
        if isinstance(value, str):
            values[column] = value[:_TEXT_LIMIT]
    values["osg_email"] = data["email"] or None
    values["osg_research_updated_at"] = data["researched_at"]
    values["osg_profile_json"] = json.dumps(data["extra"], default=str)
    # Direct write on purpose: these are connector-owned, read-only fields, and a
    # document save would fire the Customer hooks that push changes to the stores.
    frappe.db.set_value("Customer", customer, values, update_modified=False)
    return True


def profile_key(data):
    return data.get("email") or data.get("shopify_customer_id")


def merge_fields(existing, new, incoming_is_newer):
    """The profile after one more row or delivery.

    Counters take the largest value seen. For every other field a value the new row
    lacks never erases one already stored, and a stored value is replaced only when
    the incoming row is the more recent."""
    merged = dict(existing)
    for name, value in new.items():
        if name in CUMULATIVE:
            merged[name] = max(existing.get(name) or 0, value or 0)
        elif value in _EMPTY:
            continue
        elif existing.get(name) in _EMPTY or incoming_is_newer:
            merged[name] = value
    return merged


def _is_newer(existing_date, new_date, source):
    """A delivery is always the latest word. A file row is newer when its order is."""
    if source == "webhook" or not existing_date:
        return True
    return bool(new_date) and str(new_date) >= str(existing_date)


def _record_values(fields):
    values = {}
    for name, kind in COLUMN_KINDS.items():
        value = fields.get(name)
        values[name] = (value or 0) if kind in ("int", "float", "check") else value
    return values


def store_profile(data, source, customers=()):
    """Keep the profile as its own record, whether or not the person is a Customer
    here: one record per email (or Shopify customer id), every order listed, and a link
    to each Customer found. Returns the record name, or None when the row identifies
    nobody."""
    key = profile_key(data)
    if not key:
        return None
    fields = data["fields"]
    existing = frappe.db.get_value(
        PROFILE, {"profile_key": key}, ["name", "researched_at"] + list(COLUMN_KINDS), as_dict=True
    )

    if existing:
        name = existing.name
        # An older delivery leaves the profile alone, but its order is still recorded.
        stale = existing.researched_at and data["researched_at"] and data["researched_at"] < existing.researched_at
        if not stale:
            current = {k: existing.get(k) for k in COLUMN_KINDS}
            newer = _is_newer(existing.get("order_date"), fields.get("order_date"), source)
            values = _record_values(merge_fields(current, fields, newer))
            values["source"] = source
            if data["researched_at"]:
                values["researched_at"] = data["researched_at"]
            frappe.db.set_value(PROFILE, name, values)
    else:
        values = _record_values(fields)
        if data["researched_at"]:
            values["researched_at"] = data["researched_at"]
        doc = frappe.get_doc(dict(doctype=PROFILE, profile_key=key, source=source, **values))
        doc.insert(ignore_permissions=True)
        name = doc.name

    _add_order(name, fields)
    for customer in customers:
        _add_customer(name, customer)
    return name


def _add_order(profile, fields):
    order_name = fields.get("order_name")
    filters = {"parent": profile, "parenttype": PROFILE, "order_name": order_name}
    if not order_name or frappe.db.exists(PROFILE_ORDER, filters):
        return
    position = frappe.db.count(PROFILE_ORDER, {"parent": profile, "parenttype": PROFILE})
    frappe.get_doc({
        "doctype": PROFILE_ORDER, "parent": profile, "parenttype": PROFILE, "parentfield": "orders",
        "idx": position + 1, "order_name": order_name, "order_date": fields.get("order_date"),
        "order_email": fields.get("order_email"), "channel_name": fields.get("channel_name"),
    }).insert(ignore_permissions=True)


def _add_customer(profile, customer):
    if frappe.db.exists(PROFILE_CUSTOMER, {"parent": profile, "parenttype": PROFILE, "customer": customer}):
        return
    position = frappe.db.count(PROFILE_CUSTOMER, {"parent": profile, "parenttype": PROFILE})
    frappe.get_doc({
        "doctype": PROFILE_CUSTOMER, "parent": profile, "parenttype": PROFILE, "parentfield": "customers",
        "idx": position + 1, "customer": customer,
    }).insert(ignore_permissions=True)


def process(data, source):
    """Keep the profile, find every Customer this person is, and copy the profile
    onto each. Returns (record name, customers found, customers updated); the name
    is None when the row identifies nobody.

    The Customers receive the merged profile, not just this row, so a row that lacks
    a value never blanks one an earlier order supplied."""
    name = store_profile(data, source)
    if not name:
        return None, set(), 0
    record = frappe.db.get_value(PROFILE, name, ["name", "researched_at"] + list(COLUMN_KINDS), as_dict=True)
    orders = frappe.get_all(PROFILE_ORDER, filters={"parent": name, "parenttype": PROFILE}, pluck="order_name")
    merged = data_from_record(record)
    customers = find_customers(merged["email"], orders or [data["order_name"]], merged["shopify_customer_id"])
    updated = 0
    for customer in customers:
        _add_customer(name, customer)
        if apply_profile(customer, merged):
            updated += 1
    return name, customers, updated


def data_from_record(record):
    """The shape apply_profile takes, rebuilt from a stored profile record."""
    fields = {k: record.get(k) for k in COLUMN_KINDS}
    return {
        "email": record.get("email") or "", "order_name": record.get("order_name"),
        "shopify_customer_id": record.get("shopify_customer_id"), "researched_at": record.get("researched_at"),
        "age": record.get("age") or None, "gender": record.get("gender"), "persona": record.get("persona"),
        "job_title": record.get("job_title_1"), "property_value": record.get("property_value") or None,
        "city": record.get("city"), "state": record.get("state"), "country": record.get("country"),
        "fields": fields, "extra": {k: v for k, v in fields.items() if v not in _EMPTY},
    }


def link_pending_profiles(limit=2000):
    """Attach stored profiles that have no Customer yet to the Customers that have
    appeared since (a person who ordered after the profile was stored), and copy the
    profile onto them. Returns how many profiles were linked."""
    pending = frappe.db.sql(
        f"""
        SELECT p.name FROM `tab{PROFILE}` p
        WHERE NOT EXISTS (SELECT 1 FROM `tab{PROFILE_CUSTOMER}` c WHERE c.parent = p.name)
        LIMIT {int(limit)}
        """,
        pluck="name",
    )
    linked = 0
    for name in pending:
        record = frappe.db.get_value(PROFILE, name, ["name", "researched_at"] + list(COLUMN_KINDS), as_dict=True)
        orders = frappe.get_all(PROFILE_ORDER, filters={"parent": name, "parenttype": PROFILE}, pluck="order_name")
        data = data_from_record(record)
        customers = find_customers(data["email"], orders or [data["order_name"]], data["shopify_customer_id"])
        for customer in customers:
            apply_profile(customer, data)
            _add_customer(name, customer)
        linked += 1 if customers else 0
    return linked
