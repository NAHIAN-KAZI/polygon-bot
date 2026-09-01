from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity


class MockAdapter:
    """Generic mock adapter for every banking subservice without a real
    integration. The live taxonomy is fetched from the platform and can list
    40+ subservices, so this returns uniform, clearly-fake placeholder data
    instead of a hand-written mock per subservice."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        return AdapterResult(
            data={
                "mock": True,
                "subservice": subservice,
                "message": (
                    f"This is placeholder data for '{subservice}'. "
                    "Real integration is not yet available for this service."
                ),
                "payload_echo": payload,
            }
        )


mock_adapter = MockAdapter()
