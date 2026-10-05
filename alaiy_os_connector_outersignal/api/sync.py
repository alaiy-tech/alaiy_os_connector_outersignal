# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Status read for the Alaiy OS connector card. This connector only receives
deliveries, so there is nothing to trigger from here.
"""

import frappe


@frappe.whitelist()
def get_sync_status(sync_type=None):
    """Return the most recent OuterSignal Sync Log rows, newest first."""
    return frappe.get_all(
        "OuterSignal Sync Log",
        fields=[
            "name", "sync_type", "trigger", "status",
            "started_at", "finished_at",
            "items_processed", "items_created", "items_updated", "items_failed",
            "error_message",
        ],
        order_by="started_at desc",
        limit=5,
    )
