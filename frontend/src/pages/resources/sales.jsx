import { CheckCircle2, ShoppingBag, Truck, Users } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { api, apiErrorMessage } from '../../lib/api'
import { Money, Primary, Qty, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const CHANNELS = ['manual', 'direct', 'whatsapp', 'pos', 'marketplace', 'instagram']
const ORDER_STATUSES = ['draft', 'confirmed', 'partially_fulfilled', 'fulfilled', 'cancelled']

export function SalesOrdersPage() {
  const can = useAuth((state) => state.can)

  const fulfill = async (row, { reload }) => {
    try {
      await api.post(`/sales/orders/${row.id}/fulfill`)
      toast.success('Order fulfilled', `${row.order_number} was dispatched and invoiced.`)
      reload()
    } catch (error) {
      toast.error('Could not fulfil order', apiErrorMessage(error))
    }
  }

  return (
    <ResourcePage
      eyebrow="Sales"
      title="Sales orders"
      description="Confirmed demand, fulfilment status and order value across every channel."
      endpoint="/sales/orders"
      permission="sales.salesorder"
      createLabel="New sales order"
      editFields={[
        { name: 'status', label: 'Status', type: 'select', options: ORDER_STATUSES },
        { name: 'warehouse_id', label: 'Warehouse', type: 'reference', lookup: 'warehouses' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
      searchPlaceholder="Search order number, notes…"
      filters={[
        { name: 'status', label: 'All statuses', options: ORDER_STATUSES },
        { name: 'channel', label: 'All channels', options: CHANNELS },
      ]}
      emptyIcon={ShoppingBag}
      emptyTitle="No sales orders yet"
      columns={[
        { key: 'order_number', label: 'Order', render: (row) => <Primary title={row.order_number} subtitle={`${row.lines?.length ?? 0} lines`} /> },
        { key: 'customer_id', label: 'Customer', render: (row) => <Ref lookup="customers" id={row.customer_id} /> },
        { key: 'order_date', label: 'Order date', render: (row) => dateLabel(row.order_date) },
        { key: 'channel', label: 'Channel', render: (row) => <TypeBadge value={row.channel} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'total', label: 'Total', align: 'right', render: (row) => <Money value={row.total} /> },
      ]}
      rowActions={[
        {
          label: 'Fulfil order',
          icon: CheckCircle2,
          tone: 'positive',
          show: (row) => can('sales.order.fulfill') && !['fulfilled', 'cancelled'].includes(row.status),
          onClick: fulfill,
        },
      ]}
      fields={[
        { name: 'customer_id', label: 'Customer', type: 'reference', lookup: 'customers' },
        { name: 'tax_registration_id', label: 'GST registration', type: 'reference', lookup: 'taxRegistrations' },
        { name: 'place_of_supply_state_code', label: 'Place-of-supply state code', help: 'Two-digit GST state code, such as 29.' },
        { name: 'warehouse_id', label: 'Warehouse', type: 'reference', lookup: 'warehouses' },
        { name: 'order_date', label: 'Order date', type: 'date', required: true, default: 'today' },
        { name: 'channel', label: 'Channel', type: 'select', options: CHANNELS, default: 'manual', required: true },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
        {
          name: 'lines',
          label: 'Order lines',
          type: 'line_items',
          required: true,
          columns: [
            { name: 'product_id', label: 'Product', type: 'reference', lookup: 'products', required: true, flex: 2 },
            { name: 'quantity', label: 'Qty', type: 'number', required: true, default: 1, width: 'w-20' },
            { name: 'unit_price', label: 'Unit price', type: 'number', required: true, default: 0, width: 'w-28' },
            { name: 'discount', label: 'Discount', type: 'number', default: 0, width: 'w-24' },
            { name: 'tax_rate', label: 'Tax %', type: 'number', default: 0, width: 'w-20' },
            { name: 'tax_code_id', label: 'GST tax code', type: 'reference', lookup: 'taxCodes', flex: 1.5 },
          ],
        },
      ]}
    />
  )
}

const PAYMENT_TERMS = ['net_15', 'net_30', 'net_45', 'net_60', 'advance', 'cod']

export function CustomersPage() {
  return (
    <ResourcePage
      eyebrow="Sales"
      title="Customers"
      description="Buyers, credit terms and contact details for your wholesale and retail base."
      endpoint="/sales/customers"
      permission="sales.customer"
      createLabel="New customer"
      searchPlaceholder="Search customers, codes, GSTIN…"
      emptyIcon={Users}
      columns={[
        { key: 'name', label: 'Customer', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        { key: 'credit_limit', label: 'Credit limit', align: 'right', render: (row) => <Money value={row.credit_limit} /> },
        { key: 'payment_terms', label: 'Terms', render: (row) => <TypeBadge value={row.payment_terms} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'code', label: 'Customer code', required: true },
        { name: 'name', label: 'Customer name', required: true },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'gstin', label: 'GSTIN' },
        { name: 'payment_terms', label: 'Payment terms', type: 'select', options: PAYMENT_TERMS, default: 'net_30' },
        { name: 'credit_limit', label: 'Credit limit', type: 'number', default: 0 },
        { name: 'billing_address', label: 'Billing address', type: 'textarea' },
        { name: 'shipping_address', label: 'Shipping address', type: 'textarea' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function DeliveryChallansPage() {
  return (
    <ResourcePage
      eyebrow="Sales"
      title="Delivery challans"
      description="Dispatch documents that accompany goods out of the warehouse."
      endpoint="/sales/delivery-challans"
      permission="sales.deliverychallan"
      createLabel="New challan"
      searchPlaceholder="Search challan number…"
      filters={[{ name: 'status', label: 'All statuses', options: ['dispatched', 'delivered', 'returned'] }]}
      emptyIcon={Truck}
      columns={[
        { key: 'challan_number', label: 'Challan', render: (row) => <Primary title={row.challan_number} subtitle={row.notes || 'No notes'} /> },
        { key: 'order_id', label: 'Sales order', render: (row) => <Ref lookup="salesOrders" id={row.order_id} /> },
        { key: 'dispatched_date', label: 'Dispatched', render: (row) => dateLabel(row.dispatched_date) },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'warehouse_id', label: 'Warehouse', render: (row) => <Ref lookup="warehouses" id={row.warehouse_id} /> },
      ]}
      fields={[
        { name: 'order_id', label: 'Sales order', type: 'reference', lookup: 'salesOrders', required: true },
        { name: 'warehouse_id', label: 'Warehouse', type: 'reference', lookup: 'warehouses' },
        { name: 'dispatched_date', label: 'Dispatched date', type: 'date', default: 'today', required: true },
        { name: 'status', label: 'Status', type: 'select', options: ['dispatched', 'delivered', 'returned'], default: 'dispatched', required: true },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}
