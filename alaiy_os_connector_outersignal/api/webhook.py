# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Receiver for the enrichment webhook. The caller is the external platform, not a
logged-in user, so the endpoint is guest-accessible and every request must carry
a valid HMAC signature before anything is read from it.
"""

import json

import frappe
from frappe.utils import now_datetime

from alaiy_os_connector_outersignal.outersignal import profile, sync_log
from alaiy_os_connector_outersignal.outersignal.parse import (
    SIGNATURE_HEADER,
    normalize,
    verify_signature,
)

SETTINGS = "OuterSignal Connector Settings"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive():
    settings = frappe.get_single(SETTINGS)
    secret = settings.get_password("outersignal_webhook_secret", raise_exception=False)
    if not settings.is_enabled or not secret:
        frappe.throw("Webhook receiver is not enabled.", frappe.PermissionError)

    body = frappe.request.get_data()
    if not verify_signature(secret, body, frappe.get_request_header(SIGNATURE_HEADER)):
        frappe.throw("Invalid signature.", frappe.PermissionError)

    try:
        data = normalize(json.loads(body))
    except (ValueError, AttributeError, TypeError):
        sync_log.record("failed", error="Body is not a JSON object.")
        frappe.local.response["http_status_code"] = 400
        return {"ok": False, "reason": "invalid body"}

    try:
        # Kept whether or not the person is a Customer here; copied onto every
        # Customer record they are found under.
        stored, customers, updated = profile.process(data, "webhook")
    except Exception:
        frappe.db.rollback()
        sync_log.record("failed", data["order_name"], frappe.get_traceback())
        frappe.db.commit()
        raise

    if not stored:
        sync_log.record("skipped", data["order_name"], "the delivery has no email or customer id to identify the person")
    elif not customers:
        sync_log.record("success", data["order_name"], message=f"order {data['order_name']}: profile kept, no matching customer yet")
    else:
        sync_log.record(
            "success" if updated else "skipped", data["order_name"],
            None if updated else "a newer profile is already stored",
            updated=updated,
        )
    frappe.db.set_single_value(SETTINGS, "outersignal_last_received_at", now_datetime())
    return {"ok": True, "stored": bool(stored), "customers": len(customers), "updated": updated}
