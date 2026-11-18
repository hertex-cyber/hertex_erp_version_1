import { Boxes, Package, Warehouse } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { DateCell, Money, Primary, Qty, Ref, Status, TypeBadge } from '../../components/cells'
import { num } from '../../lib/format'

const UOMS = ['pcs', 'kg', 'gram', 'metre', 'box', 'set', 'pair', 'litre']
const MOVEMENT_TYPES = ['receipt', 'sale', 'return', 'adjustment', 'transfer', 'damage']

export function CategoriesPage() {
  return (
    <ResourcePage
      eyebrow="Inventory"
      title="Categories"
      description="A tidy taxonomy for products, collections and reporting."
      endpoint="/inventory/categories"
      permission="inventory.category"
      createLabel="New category"
      searchPlaceholder="Search categories…"
      emptyIcon={Boxes}
      columns={[
        { key: 'name', label: 'Category', render: (row) => <Primary title={row.name} subtitle={row.description || 'No description'} /> },
        { key: 'parent_id', label: 'Parent', render: (row) => <Ref lookup="categories" id={row.parent_id} /> },
        { key: 'created_at', label: 'Created', render: (row) => <DateCell value={row.created_at} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Category name', required: true, colSpan: 2 },
        { name: 'parent_id', label: 'Parent category', type: 'reference', lookup: 'categories' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function ProductsPage() {
  return (
    <ResourcePage
      eyebrow="Inventory"
      title="Products"
      description="The catalogue: SKUs, pricing, tax treatment and reorder thresholds."
      endpoint="/inventory/products"
      permission="inventory.product"
      createLabel="New product"
      searchPlaceholder="Search SKU, name, barcode…"
      emptyIcon={Package}
      filters={[{ name: 'uom', label: 'All units', options: UOMS }]}
      columns={[
        { key: 'name', label: 'Product', render: (row) => <Primary title={row.name} subtitle={row.sku} /> },
        { key: 'category_id', label: 'Category', render: (row) => <Ref lookup="categories" id={row.category_id} /> },
        { key: 'uom', label: 'Unit', render: (row) => <TypeBadge value={row.uom} /> },
        { key: 'sale_price', label: 'Sale price', align: 'right', render: (row) => <Money value={row.sale_price} /> },
        { key: 'purchase_price', label: 'Cost', align: 'right', render: (row) => <Money value={row.purchase_price} /> },
        { key: 'tax_rate', label: 'Tax', align: 'right', render: (row) => `${num(row.tax_rate, 1)}%` },
        { key: 'tax_code_id', label: 'GST tax code', render: (row) => row.tax_code_id ? <Ref lookup="taxCodes" id={row.tax_code_id} /> : <TypeBadge value="not mapped" /> },
        { key: 'reorder_level', label: 'Reorder at', align: 'right', render: (row) => <Qty value={row.reorder_level} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'sku', label: 'SKU', required: true },
        { name: 'name', label: 'Product name', required: true },
        { name: 'category_id', label: 'Category', type: 'reference', lookup: 'categories' },
        { name: 'uom', label: 'Unit of measure', type: 'select', options: UOMS, default: 'pcs', required: true },
        { name: 'sale_price', label: 'Sale price', type: 'number', default: 0 },
        { name: 'purchase_price', label: 'Purchase price', type: 'number', default: 0 },
        { name: 'tax_rate', label: 'Tax rate %', type: 'number', default: 0 },
        { name: 'tax_code_id', label: 'GST tax code', type: 'reference', lookup: 'taxCodes', help: 'Required for sales when GST registrations are configured.' },
        { name: 'reorder_level', label: 'Reorder level', type: 'number', default: 0 },
        { name: 'barcode', label: 'Barcode' },
        { name: 'hsn_code', label: 'HSN code' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function StockMovesPage() {
  return (
    <ResourcePage
      eyebrow="Inventory"
      title="Stock movements"
      description="Every receipt, sale, adjustment and transfer — the audit trail of inventory."
      endpoint="/inventory/stock-moves"
      createEndpoint="/inventory/stock-adjustments"
      permission="inventory.stockmove"
      createLabel="Submit adjustment"
      requireIdempotencyKey
      canEdit={false}
      canDelete={false}
      searchPlaceholder="Search reason, reference…"
      filters={[{ name: 'movement_type', label: 'All movement types', options: MOVEMENT_TYPES }]}
      columns={[
        { key: 'product_id', label: 'Product', render: (row) => <Ref lookup="products" id={row.product_id} /> },
        { key: 'movement_type', label: 'Type', render: (row) => <TypeBadge value={row.movement_type} /> },
        { key: 'status', label: 'Approval', render: (row) => <TypeBadge value={row.status === 'pending_approval' ? 'pending approval' : row.status} /> },
        {
          key: 'quantity',
          label: 'Quantity',
          align: 'right',
          render: (row) => (
            <span className={Number(row.quantity) < 0 ? 'font-bold tabular-nums text-rose-600' : 'font-bold tabular-nums text-emerald-700'}>
              {Number(row.quantity) > 0 ? '+' : ''}{num(row.quantity, 2)}
            </span>
          ),
        },
        { key: 'warehouse_id', label: 'Warehouse', render: (row) => <Ref lookup="warehouses" id={row.warehouse_id} /> },
        { key: 'unit_cost', label: 'Unit cost', align: 'right', render: (row) => <Money value={row.unit_cost} /> },
        { key: 'journal_entry_id', label: 'Journal', render: (row) => row.journal_entry_id ? <span className="font-mono text-xs" title={row.journal_entry_id}>{row.journal_entry_id.slice(0, 8)}</span> : <TypeBadge value="unposted" /> },
        { key: 'reference', label: 'Reference' },
        { key: 'created_at', label: 'When', render: (row) => <DateCell value={row.created_at} /> },
      ]}
      fields={[
        { name: 'product_id', label: 'Product', type: 'reference', lookup: 'products', required: true },
        { name: 'adjustment_date', label: 'Posting date', type: 'date', default: 'today', required: true },
        { name: 'quantity', label: 'Quantity adjustment', type: 'number', required: true, help: 'Positive increases stock; negative decreases stock.' },
        { name: 'unit_cost', label: 'Unit cost', type: 'number', required: true, help: 'The per-unit valuation used for the inventory journal.' },
        { name: 'warehouse_id', label: 'Warehouse', type: 'reference', lookup: 'warehouses' },
        { name: 'bin_id', label: 'Bin', type: 'reference', lookup: 'bins' },
        { name: 'reference', label: 'Reference' },
        { name: 'reason', label: 'Adjustment reason', type: 'textarea', required: true, colSpan: 2 },
      ]}
    />
  )
}

export function WarehousesPage() {
  return (
    <ResourcePage
      eyebrow="Warehouse"
      title="Warehouses"
      description="Physical locations where stock is received, stored and dispatched."
      endpoint="/warehouse/warehouses"
      permission="warehouse.warehouse"
      createLabel="New warehouse"
      searchPlaceholder="Search warehouses…"
      emptyIcon={Warehouse}
      columns={[
        { key: 'name', label: 'Warehouse', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
        { key: 'city', label: 'City' },
        { key: 'state', label: 'State' },
        { key: 'created_at', label: 'Added', render: (row) => <DateCell value={row.created_at} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Warehouse name', required: true },
        { name: 'code', label: 'Warehouse code', required: true },
        { name: 'city', label: 'City' },
        { name: 'state', label: 'State' },
        { name: 'address', label: 'Address', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function BinsPage() {
  return (
    <ResourcePage
      eyebrow="Warehouse"
      title="Bins"
      description="Granular storage locations inside each warehouse."
      endpoint="/warehouse/bins"
      permission="warehouse.bin"
      createLabel="New bin"
      searchPlaceholder="Search bins…"
      columns={[
        { key: 'code', label: 'Bin', render: (row) => <Primary title={row.code} subtitle={row.name || 'Unnamed bin'} /> },
        { key: 'warehouse_id', label: 'Warehouse', render: (row) => <Ref lookup="warehouses" id={row.warehouse_id} /> },
        { key: 'created_at', label: 'Added', render: (row) => <DateCell value={row.created_at} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'warehouse_id', label: 'Warehouse', type: 'reference', lookup: 'warehouses', required: true },
        { name: 'code', label: 'Bin code', required: true },
        { name: 'name', label: 'Bin name', colSpan: 2 },
      ]}
    />
  )
}
