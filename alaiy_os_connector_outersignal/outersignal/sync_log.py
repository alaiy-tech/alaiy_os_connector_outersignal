# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""One OuterSignal Sync Log row per webhook delivery. No personal data goes in it."""

import frappe
from frappe.utils import now_datetime


def record(status, order_name=None, error=None, updated=0):
    log = frappe.new_doc("OuterSignal Sync Log")
    log.sync_type = "webhook"
    log.trigger = "webhook"
    log.status = status
    log.started_at = log.finished_at = now_datetime()
    log.items_processed = 1
    log.items_updated = updated
    log.items_failed = 1 if status == "failed" else 0
    log.error_message = (error or "")[:2000]
    log.log_messages = f"order {order_name}" if order_name else ""
    log.insert(ignore_permissions=True)
    return log.name
