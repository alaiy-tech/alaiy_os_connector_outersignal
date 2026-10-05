# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Readiness check. The platform calls us, so there is no outbound request to try;
this reports whether the receiver can accept a delivery and when the last one
arrived. Wired into the registry via connector_meta["test_method"]. Always
returns {"success": bool, "message": str} and never raises to the caller.
"""

import frappe


@frappe.whitelist()
def test_connection():
    doc = frappe.get_single("OuterSignal Connector Settings")
    secret = doc.get_password("outersignal_webhook_secret", raise_exception=False)

    if not doc.is_enabled:
        return {"success": False, "message": "OuterSignal is not enabled."}
    if not secret:
        return {"success": False, "message": "Signing Secret is not set."}

    last = doc.outersignal_last_received_at
    if not last:
        return {"success": True, "message": "Ready. No delivery received yet."}
    return {"success": True, "message": f"Ready. Last delivery received {last}."}
