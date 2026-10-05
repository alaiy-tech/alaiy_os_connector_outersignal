# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Match an enrichment delivery to a Customer and store the profile on it.

An order name such as "#1042" is only unique inside one store, so it can point at
several Customers on a bench that hosts several stores. The email narrows that
down; when it cannot, the delivery is skipped rather than written to a guess.
"""

import json

import frappe

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


def find_customer(email, order_name):
    """Return (customer, None) on a single match, else (None, reason)."""
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


def apply_profile(customer, data):
    """Write the enrichment values. Returns False when a newer profile is stored."""
    stored = frappe.db.get_value("Customer", customer, "osg_research_updated_at")
    if stored and data["researched_at"] and data["researched_at"] < stored:
        return False

    values = {column: data[key] for key, column in FIELD_MAP.items()}
    values["osg_email"] = data["email"] or None
    values["osg_research_updated_at"] = data["researched_at"]
    values["osg_profile_json"] = json.dumps(data["extra"], default=str)
    # Direct write on purpose: these are connector-owned, read-only fields, and a
    # document save would fire the Customer hooks that push changes to the stores.
    frappe.db.set_value("Customer", customer, values, update_modified=False)
    return True
