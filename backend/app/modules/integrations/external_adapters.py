from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

DEGRADED_SIMULATED = "degraded_simulated"
SIMULATED = "simulated"


@dataclass(slots=True)
class ConnectionResult:
    provider: str
    status: str
    is_configured: bool
    detail: str
    checked_fields: list[str] = field(default_factory=list)


class ExternalAdapter:
    def __init__(
        self,
        *,
        provider: str,
        required_fields: tuple[str, ...],
        credentials: Mapping[str, str],
    ) -> None:
        self.provider = provider
        self.required_fields = tuple(required_fields)
        self._credentials = dict(credentials)

    @property
    def missing_fields(self) -> list[str]:
        return [name for name in self.required_fields if not self._credentials.get(name)]

    @property
    def is_configured(self) -> bool:
        return not self.missing_fields

    async def test_connection(self) -> ConnectionResult:
        checked = list(self.required_fields)
        if not self.is_configured:
            missing = ", ".join(self.missing_fields)
            return ConnectionResult(
                provider=self.provider,
                status=DEGRADED_SIMULATED,
                is_configured=False,
                detail=(
                    f"{self.provider} credentials are not configured ({missing}); "
                    "simulated check only, no external call made"
                ),
                checked_fields=checked,
            )
        return ConnectionResult(
            provider=self.provider,
            status=SIMULATED,
            is_configured=True,
            detail=(
                f"{self.provider} credentials are present; simulated check only, "
                "no external call made"
            ),
            checked_fields=checked,
        )


class GstPortalAdapter(ExternalAdapter):
    pass


class EInvoicePortalAdapter(ExternalAdapter):
    pass


class BankFeedAdapter(ExternalAdapter):
    pass


class PaymentGatewayAdapter(ExternalAdapter):
    pass


class OcrAdapter(ExternalAdapter):
    pass


_ADAPTERS: dict[str, type[ExternalAdapter]] = {
    "gst_portal": GstPortalAdapter,
    "e_invoice_portal": EInvoicePortalAdapter,
    "bank_feed": BankFeedAdapter,
    "payment_gateway": PaymentGatewayAdapter,
    "ocr": OcrAdapter,
}


def build_adapter(
    *,
    provider: str,
    required_fields: tuple[str, ...],
    credentials: Mapping[str, str],
) -> ExternalAdapter:
    adapter_class = _ADAPTERS.get(provider, ExternalAdapter)
    return adapter_class(
        provider=provider,
        required_fields=required_fields,
        credentials=credentials,
    )
