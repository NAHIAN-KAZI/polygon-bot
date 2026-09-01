from app.banking import adapter_map
from app.banking.adapters.base import AdapterResult, BankingAdapter
from app.banking.adapters.mock import mock_adapter
from app.banking.adapters.real import REAL_ADAPTERS
from app.banking.identity import CustomerIdentity


def get_adapter(adapter_name: str) -> BankingAdapter:
    if adapter_name == "mock":
        return mock_adapter
    if adapter_name in REAL_ADAPTERS:
        return REAL_ADAPTERS[adapter_name]
    raise ValueError(f"Unknown adapter name: {adapter_name}")


async def fulfill_banking_service(
    customer_identity: CustomerIdentity,
    jwt: str | None,
    category: str,
    service: str,
    subservice: str | None,
    payload: dict | None,
) -> AdapterResult:
    adapter_name = adapter_map.get_adapter_name(category, service, subservice)
    adapter = get_adapter(adapter_name)
    return await adapter.fulfill(customer_identity, jwt, subservice or service, payload)
