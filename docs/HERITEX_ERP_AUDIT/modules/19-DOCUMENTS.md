# 19 — Documents & Files (Attachment, PDF Generation, Storage)

**Module owner:** Platform (Documents)
**Rank:** cross-cutting but essential — every invoice, PO, payslip, GRN and e-way bill is a file that must exist, be findable, and be legal
**Current state:** the word "attachment" appears in the plan; **no document/attachment code exists** — no upload, no storage, no PDF rendering
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the lifecycle of every file and generated document: uploads (PO PDFs from suppliers, GST certificates, signed challans, employee documents), **server-rendered PDFs** for outbound documents (invoice, PO, payslip, GRN, delivery challan, credit note), storage, retrieval, retention, and the audit trail proving a document existed.

**In scope:** attachment table + upload/download, virus-scanning hook, storage abstraction (local/S3), PDF templates, PDF generation for all documents, document-linking to any entity, versioning, retention/legal-hold, watermarks.
**Out of scope (v1):** full DMS/OCR of scanned supplier invoices (OCR hook only), e-signature workflows, collaborative editing, in-app document viewer beyond browser PDF.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| Attachment/document model | ❌ none |
| Upload endpoint | ❌ none |
| Storage abstraction | ❌ none |
| PDF generation | ❌ none — invoice/PO data lives only in JSON/DB; no printable artefact |
| Templates | ❌ none |
| Document versions / legal hold | ❌ none |

**Headline:** today the system can create an invoice in the database but **cannot produce the invoice as a file**. For a GST business that's a functional gap (module 17 prints IRN/QR on the PDF) and a customer-facing one (they need to send invoices). This is greenfield.

---

## 3. Domain model

### 3.1 Storage + attachment
```
attachments
  id, tenant_id, entity_type (invoice|po|payslip|grn|customer|product|lead...),
  entity_id, file_name, mime_type, size_bytes, storage_key (local path or S3 key),
  checksum_sha256, is_public (bool), uploaded_by, virus_scan_status [pending|clean|infected|skipped],
  retention_until, legal_hold (bool), version, parent_document_id (for supersede chains)

document_templates
  key (invoice_default|po_default|payslip_default|...), name, html_template (Jinja2),
  css, paper_size [A4|A5|thermal80|thermal58], is_default, org_branding_json

document_generations
  template_key, entity_type, entity_id, storage_key, rendered_at,
  requested_by, watermark, is_reprint, checksum
```

### 3.2 Storage abstraction
```
class StorageBackend(Protocol):
    def put(key, data, content_type) -> str
    def get(key) -> bytes
    def delete(key) -> None
    def signed_url(key, ttl) -> str      # S3 presigned / local served through API
```
Default: local `MEDIA_ROOT`; `S3_BACKEND` flips it. Same key scheme: `tenant/{tenant_id}/{entity_type}/{entity_id}/{uuid}-{name}`.

### 3.3 PDF rendering pipeline
```
entity → context builder (loads the entity + related + branding + tax/QR data)
      → Jinja2 HTML (A4 template)
      → WeasyPrint (HTML/CSS → PDF; supports Indian number formatting, GST fields, QR image)
      → store via StorageBackend + document_generations row (immutable artefact)
```
**Why WeasyPrint:** no headless browser dependency, deterministic pagination, CSS `@page`. Thermal (80/58 mm) uses a narrow CSS template. A reprint is a *new generation row* with `is_reprint=true` and a watermark — the original is never overwritten (audit).

---

## 4. State machines

### 4.1 Attachment (virus scan gate)
```
uploaded  --scan_start--> scanning
scanning  --clean-->      available     guard: scanner returned clean
scanning  --infected-->   quarantined    guard: scanner flagged → deleted + alerted
scanning  --skip-->       available     guard: type not scannable (none today)
available --expire-->     expired       guard: retention_until passed AND not legal_hold
```
### 4.2 Generated document
```
requested  --render-->  rendered   guard: template + context valid
rendered   --supersede--> superseded  (a new version generated; old kept)
```
Legal hold pins both to `hold` and blocks expiry.

---

## 5. API surface

**All new:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `POST /documents/upload` | POST | `documents.upload` | multipart upload, attaches to entity |
| `GET /documents/{id}` | GET | `documents.read` | metadata + signed URL |
| `GET /documents/{id}/content` | GET | `documents.read` | stream file |
| `GET /documents?entity=invoice&id=123` | GET | `documents.read` | list by entity |
| `DELETE /documents/{id}` | DELETE | `documents.delete` | soft delete (blocked by legal hold) |
| `POST /documents/generate/{doc_type}/{entity_id}` | POST | per-module read | render PDF (invoice/po/payslip/grn) |
| `GET /documents/generate/{doc_type}/{entity_id}/preview` | GET | per-module read | HTML preview |
| `GET/POST /documents/templates` | GET/POST | `system.settings.manage` | template management |
| `POST /documents/{id}/legal-hold` | POST | `documents.admin` | pin/release |

---

## 6. Business rules

- **DC-01** — Every generated document is immutable; edits create a new version and mark the old `superseded`.
- **DC-02** — Reprints carry a "REPRINT" watermark (and reprint count) — required to distinguish originals for auditors.
- **DC-03** — Uploads are virus-scanned before becoming `available`; infected files are quarantined and reported.
- **DC-04** — Documents linked to posted financial records (invoice, payslip, GRN) are subject to **retention** (8 years for tax docs) and cannot be deleted while `legal_hold`.
- **DC-05** — Storage keys are tenant-prefixed; a signed URL never crosses tenants.
- **DC-06** — GST documents include the IRN, ack number, QR and signature where e-invoicing applied (module 17 GT-05).
- **DC-07** — The rendered PDF checksum is stored so a re-download proves integrity.
- **DC-08** — Thermal PDFs (POS) use the 80mm/58mm template; A4 for everything else.
- **DC-09** — Branding (logo, address, GSTIN) comes from tenant settings, not hardcoded.

---

## 7. Workflows (end-to-end)

### 7.1 Outbound invoice PDF
1. Invoice issued; if e-invoiced, IRN/QR present (module 17).
2. `POST /documents/generate/invoice/{id}` → context builder → HTML → WeasyPrint → PDF.
3. Stored + `document_generations` row; downloadable + sendable (module 12 WhatsApp/SMS attach).
4. Reprint later → new row with watermark.

### 7.2 Inbound supplier document
1. Buyer uploads the supplier's PO-confirmation / GST certificate to the vendor entity.
2. Scan → `available` → linked in the vendor 360 view.
3. Retention set; legal hold pinning if disputed.

### 7.3 Payslip batch
1. Payroll run completes → generate payslip PDFs for all employees.
2. Stored per employee; deliverable via portal/WhatsApp/email.

---

## 8. Accounting impact

None directly — but documents are the **evidence layer** for the ledger. An audit reconstructs from journals (BR-10) and the supporting documents must exist and be retrievable for the same period. Retention (DC-04) is set to match statutory financial-document obligations.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally** | Print invoice/PO, attach documents | Server-rendered, versioned, watermark reprints | Tally's print designer |
| **Zoho Books** | PDF invoices, attachments, portal | Same-DB generation from live data, GST-complete | Zoho's e-sign |
| **SAP B1** | Print layouts, attachments | Zero-config templates, SMB-simple | SAP CR (Crystal Reports) |
| **Odoo** | QWeb PDF reports, attachments | India GST/thermal templates | Odoo's report designer |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **OCR of supplier invoices** (extract amount/GSTIN/date) | pre-fills 3-way match | human confirms before posting |
| 1 | **Document classification** (which attachment is a GST cert vs PO) | auto-links to the right entity | suggestion + confidence |
| 2 | "Show me last month's PO PDFs" | retrieval | read-only |

---

## 11. Non-functional & security

- **Storage:** local by default, S3 optional; content-type validated; max upload size (e.g. 25 MB).
- **Security:** signed URLs with short TTL (DC-05); virus scan (DC-03); no path traversal in keys; PII documents DPDP-masked in logs.
- Performance: PDF render < 1 s typical; batch payslips streamed.
- Retention: 8 years financial docs; `legal_hold` overrides deletion.
- Audit: every upload, generation, deletion, legal hold.

---

## 12. Reporting & analytics

Documents per entity type, storage used per tenant, scan failure rate, reprint count (audit signal — many reprints can indicate a process leak), expiring documents.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `invoice.posted` | in | auto-generate PDF |
| `payslip.created` | in | generate payslip PDFs |
| `grn.received` | in | generate GRN / delivery challan |
| generated PDF | out | WhatsApp/email send (module 12) |
| supplier upload | in | 3-way match (module 02) |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (storage + attachments)** | `attachments`, StorageBackend (local/S3), upload/download, virus-scan hook | DC-03/05 tests |
| **M2 (invoice + PO PDF)** | templates, Jinja2 context, WeasyPrint, A4 + GST fields + QR | DC-06/07/09; PDF renders with IRN/QR |
| **M3 (payslip + GRN + thermal)** | payslip batch, GRN/challan, 80/58mm thermal | DC-08 tests |
| **M4 (versioning + legal hold + retention)** | supersede chain, watermark reprints, retention job | DC-01/02/04 tests |
| **M5 (OCR hook)** | supplier-invoice OCR → match pre-fill | OCR suggestion accuracy on fixtures |

Order: **M1 → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Upload → scanned → download via signed URL (M1).
- Infected file quarantined, not available (M1).
- Invoice PDF contains IRN/QR when e-invoiced (M2).
- Reprint watermarked, original immutable (M4).
- Retention job expires non-hold docs only (M4).
- Tenant isolation: signed URL from tenant A cannot read tenant B (M1).

---

## 16. Migration & rollout

- No historic files to migrate (greenfield) — start clean.
- Seed default templates (invoice/PO/payslip/GRN/challan).
- S3 optional; start local, flip per-tenant when volume grows.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No PDF for invoices | can't send/print legally-required docs | M2 blocker |
| Unsigned URL without tenant check | data leak | DC-05 signed+scoped |
| No legal hold | retention deletes evidence | DC-04 / M4 |
| Fonts (Devanagari/GST) missing in WeasyPrint | broken PDFs | bundle fonts, test |

---

## 18. Definition of Done

- [ ] M1 attachments + storage (local/S3) + scan
- [ ] M2 invoice/PO PDF with GST + QR
- [ ] M3 payslip + GRN + thermal
- [ ] M4 versioning + watermark + legal hold + retention
- [ ] M5 OCR hook
- [ ] RBAC, signed URLs, audit, DPDP
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated