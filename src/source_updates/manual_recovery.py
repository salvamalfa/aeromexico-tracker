"""Explicit browser handoff after failed collection; never a successful download."""


def plan(item, failure, run_id):
    return {
        "status": "pending_official_browser_attempt",
        "product": item["product"],
        "requested_period": item["period"],
        "official_url": item["url"],
        "failed_collection_run_id": run_id,
        "failed_item_id": item["id"],
        "programmatic_http_status": failure.get(
            "http_status", failure.get("failed_response", {}).get("http_status")
        ),
        "browser_owner": "agent_if_available_otherwise_dot_cloud_browser",
        "steps": [
            "Open the official page with the supported browser and use its normal download UI",
            "Stop at tool denials, authentication, CAPTCHA or security warnings requiring permission",
            "Retain the downloaded file unchanged; record source URL, actual observation time and method",
            "Verify readable bytes, file type, document identity, period, units, coverage and SHA-256",
            "Transfer through supported Library handoff; consumer verifies bytes and hash before import",
            "Use the existing manual-import contract and replay; never call reconstructed text an original",
        ],
        "if_unavailable": (
            "Record the exact browser/tool/access blocker; do not claim all acquisition routes exhausted"
        ),
        "manual_download_completed": False,
        "network_requests": 0,
        "activation": "none",
        "publication": "not_authorized",
    }
