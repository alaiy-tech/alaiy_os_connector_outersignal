"""
Single source of truth for this connector's registration metadata.
Consumed by setup/install.py → upserted into alaiy_os's OS Connector Registry.
"""

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
}
