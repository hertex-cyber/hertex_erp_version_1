import { useState } from 'react'
import { BadgeCheck, BadgeIndianRupee, ClipboardList, PackageCheck, Receipt, ShoppingCart, Truck } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import GSTTaxLinesModal from '../finance/GSTTaxLinesModal'
import { api, apiErrorMessage } from '../../lib/api'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel, today } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const TERMS = ['net_15', 'net_30', 'net_45', 'net_60', 'advance', 'cod']
const PO_STATUSES = ['draft', 'pending_approval', 'approved', 'partially_received', 'received', 'cancelled']

export function VendorsPage() {
  return (
    <ResourcePage
      eyebrow="Procurement"
      title="Vendors"
      description="Supply partners, terms and performance signals."
      endpoint="/procurement/vendors"
      permission="procurement.vendor"
      createLabel="New vendor"
      searchPlaceholder="Search vendors, codes…"
      columns={[
        { key: 'name', label: 'Vendor', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        { key: 'rating', label: 'Rating', align: 'right', render: (row) => <span className="font-bold text-gold">{Number(row.rating ?? 0).toFixed(1)} ★</span> },
        { key: 'payment_terms', label: 'Terms', render: (row) => <TypeBadge value={row.payment_terms} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'code', label: 'Vendor code', required: true },
        { name: 'name', label: 'Vendor name', required: true },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'gstin', label: 'GSTIN' },
        { name: 'payment_terms', label: 'Payment terms', type: 'select', options: TERMS, default: 'net_30' },
        { name: 'rating', label: 'Rating (0–5)', type: 'number', default: 0, min: 0 },
        { name: 'address', label: 'Address', type: 'textarea', colSpan: 2 },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function RequisitionsPage() {
  return (
    <ResourcePage
      eyebrow="Procurement"
      title="Requisitions"
      description="Internal requests that kick off the buying cycle."
      endpoint="/procurement/requisitions"
      permission="procurement.requisition"
      createLabel="New requisition"
      searchPlaceholder="Search requisitions…"
      filters={[{ name: 'status', label: 'All statuses', options: ['pending', 'approved', 'rejected', 'fulfilled'] }]}
      emptyIcon={ClipboardList}
      columns={[
        { key: 'requisition_number', label: 'Requisition', render: (row) => <Primary title={row.requisition_number} subtitle={row.department || 'No department'} /> },
        { key: 'requested_by_id', label: 'Requested by', render: (row) => <Ref lookup="users" id={row.requested_by_id} /> },
        { key: 'required_date', label: 'Required by', render: (row) => dateLabel(row.required_date) },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'created_at', label: 'Created', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'requested_by_id', label: 'Requested by', type: 'reference', lookup: 'users' },
        { name: 'department', label: 'Department' },
        { name: 'required_date', label: 'Required date', type: 'date', default: 'today' },
        { name: 'status', label: 'Status', type: 'select', options: ['pending', 'approved', 'rejected', 'fulfilled'], default: 'pending', required: true },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function PurchaseOrdersPage() {
  const can = useAuth((state) => state.can)

  const approve = async (row, { reload }) => {
    try {
      await api.post(`/procurement/purchase-orders/${row.id}/approve`)
      toast.success('Purchase order approved', `${row.po_number} is ready to receive.`)
      reload()
    } catch (error) {
      toast.error('Could not approve', apiErrorMessage(error))
    }
  }

  const receive = async (row, { reload }) => {
    try {
      await api.post(`/procurement/purchase-orders/${row.id}/receive`, {
        purchase_order_id: row.id,
        received_date: today(),
        notes: 'Received from web console',
      })
      toast.success('Goods received and accrued', `${row.po_number} stock was updated and GRNI posted to the ledger.`)
      reload()
    } catch (error) {
      toast.error('Could not receive goods', apiErrorMessage(error))
    }
  }

  return (
    <ResourcePage
      eyebrow="Procurement"
      title="Purchase orders"
      description="Approved commitments to suppliers, with receiving built in."
      endpoint="/procurement/purchase-orders"
      permission="procurement.purchaseorder"
      createLabel="New purchase order"
      editFields={[
        { name: 'status', label: 'Status', type: 'select', options: PO_STATUSES },
        { name: 'expected_date', label: 'Expected date', type: 'date' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
      searchPlaceholder="Search purchase orders…"
      filters={[{ name: 'status', label: 'All statuses', options: PO_STATUSES }]}
      emptyIcon={ShoppingCart}
      columns={[
        { key: 'po_number', label: 'PO', render: (row) => <Primary title={row.po_number} subtitle={`${row.lines?.length ?? 0} lines`} /> },
        { key: 'vendor_id', label: 'Vendor', render: (row) => <Ref lookup="vendors" id={row.vendor_id} /> },
        { key: 'order_date', label: 'Ordered', render: (row) => dateLabel(row.order_date) },
        { key: 'expected_date', label: 'Expected', render: (row) => dateLabel(row.expected_date) },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'total', label: 'Total', align: 'right', render: (row) => <Money value={row.total} /> },
      ]}
      rowActions={[
        {
          label: 'Approve',
          icon: BadgeCheck,
          tone: 'positive',
          show: (row) => can('procurement.po.approve') && ['pending_approval', 'draft'].includes(row.status),
          onClick: approve,
        },
        {
          label: 'Receive goods',
          icon: PackageCheck,
          tone: 'positive',
          show: (row) => can('procurement.grn.create') && ['approved', 'partially_received'].includes(row.status),
          onClick: receive,
        },
      ]}
      fields={[
        { name: 'vendor_id', label: 'Vendor', type: 'reference', lookup: 'vendors', required: true },
        { name: 'requisition_id', label: 'Requisition', type: 'reference', lookup: 'requisitions' },
        { name: 'order_date', label: 'Order date', type: 'date', default: 'today', required: true },
        { name: 'expected_date', label: 'Expected date', type: 'date' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
        {
          name: 'lines',
          label: 'Purchase order lines',
          type: 'line_items',
          required: true,
          columns: [
            { name: 'product_id', label: 'Product', type: 'reference', lookup: 'products', required: true, flex: 2 },
            { name: 'quantity', label: 'Qty', type: 'number', required: true, default: 1, width: 'w-20' },
            { name: 'unit_price', label: 'Unit price', type: 'number', required: true, default: 0, width: 'w-28' },
            { name: 'description', label: 'Note', type: 'text', flex: 1.5 },
          ],
        },
      ]}
    />
  )
}

export function VendorInvoicesPage() {
  const can = useAuth((state) => state.can)
  const [taxTarget, setTaxTarget] = useState(null)
  const [reloadList, setReloadList] = useState(null)

  const approve = async (row, { reload }) => {
    try {
      await api.post(`/procurement/vendor-invoices/${row.id}/approve`)
      toast.success('Invoice approved', `${row.invoice_number} is approved for payment.`)
      reload()
    } catch (error) {
      toast.error('Could not approve invoice', apiErrorMessage(error))
    }
  }

  return (
    <>
    <ResourcePage
      eyebrow="Procurement"
      title="Vendor invoices"
      description="Supplier bills awaiting approval, matched to purchase orders."
      endpoint="/procurement/vendor-invoices"
      permission="procurement.vendorinvoice"
      createLabel="New vendor invoice"
      searchPlaceholder="Search invoice numbers…"
      filters={[{ name: 'status', label: 'All statuses', options: ['pending', 'approved', 'paid', 'disputed'] }]}
      emptyIcon={Receipt}
      columns={[
        { key: 'invoice_number', label: 'Invoice', render: (row) => <Primary title={row.invoice_number} subtitle={dateLabel(row.issue_date)} /> },
        { key: 'vendor_id', label: 'Vendor', render: (row) => <Ref lookup="vendors" id={row.vendor_id} /> },
        { key: 'due_date', label: 'Due', render: (row) => dateLabel(row.due_date) },
        { key: 'amount', label: 'Amount', align: 'right', render: (row) => <Money value={row.amount} /> },
        { key: 'tax_amount', label: 'Tax', align: 'right', render: (row) => <Money value={row.tax_amount} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      ]}
      rowActions={[
        {
          label: 'Manage GST lines',
          icon: BadgeIndianRupee,
          show: (row) => can('procurement.vendorinvoice.update') && row.status === 'pending',
          onClick: (row, { reload }) => {
            setReloadList(() => reload)
            setTaxTarget(row)
          },
        },
        {
          label: 'Approve invoice',
          icon: BadgeCheck,
          tone: 'positive',
          show: (row) => can('procurement.vendorinvoice.update') && row.status === 'pending',
          onClick: approve,
        },
      ]}
      fields={[
        { name: 'vendor_id', label: 'Vendor', type: 'reference', lookup: 'vendors', required: true },
        { name: 'purchase_order_id', label: 'Purchase order', type: 'reference', lookup: 'purchaseOrders' },
        { name: 'invoice_number', label: 'Invoice number', required: true },
        { name: 'issue_date', label: 'Issue date', type: 'date', default: 'today', required: true },
        { name: 'due_date', label: 'Due date', type: 'date' },
        { name: 'status', label: 'Status', type: 'select', options: ['pending', 'approved', 'paid', 'disputed'], default: 'pending' },
        { name: 'amount', label: 'Amount', type: 'number', default: 0 },
        { name: 'tax_amount', label: 'Tax amount', type: 'number', default: 0 },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
    <GSTTaxLinesModal
      open={Boolean(taxTarget)}
      invoice={taxTarget}
      invoiceType="vendor"
      onClose={() => setTaxTarget(null)}
      onSaved={() => reloadList?.()}
    />
    </>
  )
}

const TRUCK_ICON = Truck
void TRUCK_ICON
