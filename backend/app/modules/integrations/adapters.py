"""Outbound channel adapters used by the Engage bridge."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("hertex.engage_bridge")


@dataclass(slots=True)
class DeliveryResult:
    status: str
    external_id: Optional[str] = None
    detail: str = ""


class WhatsAppCloudAdapter:
    """Meta WhatsApp Cloud API adapter.

    Without credentials the adapter degrades to ``simulated`` so local
    development and tests never call Meta.  Once ``WHATSAPP_TOKEN`` and
    ``WHATSAPP_PHONE_NUMBER_ID`` are set, messages are sent for real.
    """

    channel = "whatsapp"

    def __init__(self) -> None:
        self.token = settings.WHATSAPP_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_base = settings.WHATSAPP_API_BASE.rstrip("/")
        self.api_version = settings.WHATSAPP_API_VERSION

    @property
    def configured(self) -> bool:
        return bool(self.token and self.phone_number_id)

    def _payload(self, to: str, body: str, template: str | None) -> dict[str, Any]:
        if template:
            return {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": "en"},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": body}]}
                    ],
                },
            }
        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }

    async def send(
        self, *, to: str, body: str, template: str | None = None
    ) -> DeliveryResult:
        if not self.configured:
            return DeliveryResult(
                status="simulated",
                detail="WhatsApp credentials are not configured; message was not sent",
            )
        url = f"{self.api_base}/{self.api_version}/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url, headers=headers, json=self._payload(to, body, template)
                )
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp send failed: %s", exc)
            return DeliveryResult(status="failed", detail=f"Network error: {exc}")

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_success:
            provider_id = (data.get("messages") or [{}])[0].get("id")
            return DeliveryResult(
                status="sent", external_id=provider_id, detail="Delivered to WhatsApp Cloud API"
            )
        error = (data.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        logger.warning("WhatsApp send rejected: %s", error)
        return DeliveryResult(status="failed", detail=error)
