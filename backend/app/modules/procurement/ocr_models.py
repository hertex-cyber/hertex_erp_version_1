from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.schemas import ORMModel
from app.db.base import TenantBaseModel


class OCRInvoiceDraft(TenantBaseModel):
    __tablename__ = "procurement_ocr_invoice_drafts"

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="local_stub")
    credential_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    vendor_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    vendor_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_vendors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    gstin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    confirmed_invoice_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_vendor_invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class OCRSubmitRequest(ORMModel):
    text: Optional[str] = None
    document: Optional[dict[str, Any]] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    provider: str = "auto"

    @model_validator(mode="after")
    def validate_source(self):
        if not self.text and not self.document:
            raise ValueError("Provide text or a JSON document")
        return self


class OCRConfirmRequest(ORMModel):
    vendor_id: Optional[UUID] = None
    purchase_order_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[date] = None
    amount: Optional[Decimal] = Field(default=None, ge=0)
    tax_amount: Optional[Decimal] = Field(default=None, ge=0)
    gstin: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class OCRRejectRequest(ORMModel):
    reason: str = Field(min_length=1, max_length=500)


class OCRDraftRead(ORMModel):
    id: UUID
    source_type: str
    source_digest: str
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    provider: str
    credential_key: Optional[str] = None
    vendor_name: str
    vendor_id: Optional[UUID] = None
    invoice_number: str
    invoice_date: date
    amount: Decimal
    tax_amount: Decimal
    gstin: Optional[str] = None
    confidence: Decimal
    status: str
    confirmed_invoice_id: Optional[UUID] = None
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    is_active: bool
    created_at: datetime
