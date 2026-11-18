"""
Single source of truth for this connector's registration metadata.
Consumed by setup/install.py → upserted into alaiy_os's OS Connector Registry.
"""

# Columns of OuterSignal Sync Log, named the way the Connector Health page reads them.
_LOG_FIELDS = {
    "processed": "items_processed",
    "changed": ["items_created", "items_updated"],
    "failed": "items_failed",
    "error": "error_message",
}

connector_meta = {
    "connector_id": "outersignal",
    "connector_name": "OuterSignal",
    "connector_app": "alaiy_os_connector_outersignal",
    # Customer intelligence arrives from the platform; nothing is sold to or
    # bought from it, and "channel" is the closer of the two registry values.
    "connector_type": "channel",
    "description": "Customer intelligence: enriched buyer profiles stored on the Customer",
    "icon": "users",
    "icon_url": "",
    "settings_doctype": "OuterSignal Connector Settings",
    "test_method": "alaiy_os_connector_outersignal.api.test_connection.test_connection",
    # Receive-only: no sync slots are mapped, only the status read.
    "sync_status_method": "alaiy_os_connector_outersignal.api.sync.get_sync_status",
    "is_enabled": 0,
    "connection_status": "untested",
    "health": [
        # Both functions are driven from outside (a webhook delivery, an uploaded file),
        # so neither has an interval and neither can be overdue.
        {
            "key": "webhook",
            "label": "Webhook deliveries",
            "direction": "pull",
            "log_doctype": "OuterSignal Sync Log",
            "log_filter": {"sync_type": "webhook"},
            "fields": _LOG_FIELDS,
            "scheduled": False,
            "expects_rows": False,
        },
        {
            "key": "import",
            "label": "File import",
            "direction": "pull",
            "log_doctype": "OuterSignal Sync Log",
            "log_filter": {"sync_type": "import"},
            "fields": _LOG_FIELDS,
            "scheduled": False,
            "expects_rows": False,
        },
    ],
}
