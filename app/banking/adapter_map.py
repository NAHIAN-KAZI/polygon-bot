REAL_ADAPTER_SUBSERVICE_IDS = {"transaction_history"}


def get_adapter_name(category_id: str, service_id: str, subservice_id: str | None = None) -> str:
    if subservice_id in REAL_ADAPTER_SUBSERVICE_IDS:
        return f"real:{subservice_id}"
    if service_id in REAL_ADAPTER_SUBSERVICE_IDS:
        return f"real:{service_id}"
    return "mock"


def requires_identity(category_id: str, service_id: str, subservice_id: str | None = None) -> bool:
    return True
