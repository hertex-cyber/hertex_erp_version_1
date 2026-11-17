import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import { LoadingBlock, ToastHost } from './components/ui'
import { useAuth } from './store/auth'
import { LoginPage, RegisterPage } from './pages/Auth'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Stock = lazy(() => import('./pages/Stock'))
const Reports = lazy(() => import('./pages/Reports'))
const Pos = lazy(() => import('./pages/Pos'))
const Support = lazy(() => import('./pages/Support'))
const Assistant = lazy(() => import('./pages/Assistant'))
const NotFound = lazy(() => import('./pages/NotFound'))

const CompaniesPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.CompaniesPage })))
const ContactsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.ContactsPage })))
const LeadsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.LeadsPage })))
const DealsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.DealsPage })))
const ActivitiesPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.ActivitiesPage })))

const CategoriesPage = lazy(() => import('./pages/resources/inventory').then((module) => ({ default: module.CategoriesPage })))
const ProductsPage = lazy(() => import('./pages/resources/inventory').then((module) => ({ default: module.ProductsPage })))
const StockMovesPage = lazy(() => import('./pages/resources/inventory').then((module) => ({ default: module.StockMovesPage })))
const WarehousesPage = lazy(() => import('./pages/resources/inventory').then((module) => ({ default: module.WarehousesPage })))
const BinsPage = lazy(() => import('./pages/resources/inventory').then((module) => ({ default: module.BinsPage })))

const SalesOrdersPage = lazy(() => import('./pages/resources/sales').then((module) => ({ default: module.SalesOrdersPage })))
const CustomersPage = lazy(() => import('./pages/resources/sales').then((module) => ({ default: module.CustomersPage })))
const DeliveryChallansPage = lazy(() => import('./pages/resources/sales').then((module) => ({ default: module.DeliveryChallansPage })))

const VendorsPage = lazy(() => import('./pages/resources/procurement').then((module) => ({ default: module.VendorsPage })))
const RequisitionsPage = lazy(() => import('./pages/resources/procurement').then((module) => ({ default: module.RequisitionsPage })))
const PurchaseOrdersPage = lazy(() => import('./pages/resources/procurement').then((module) => ({ default: module.PurchaseOrdersPage })))
const VendorInvoicesPage = lazy(() => import('./pages/resources/procurement').then((module) => ({ default: module.VendorInvoicesPage })))

const InvoicesPage = lazy(() => import('./pages/resources/finance').then((module) => ({ default: module.InvoicesPage })))
const PaymentsPage = lazy(() => import('./pages/resources/finance').then((module) => ({ default: module.PaymentsPage })))
const AccountsPage = lazy(() => import('./pages/resources/finance').then((module) => ({ default: module.AccountsPage })))
const JournalEntriesPage = lazy(() => import('./pages/resources/finance').then((module) => ({ default: module.JournalEntriesPage })))
const BankAccountsPage = lazy(() => import('./pages/resources/finance').then((module) => ({ default: module.BankAccountsPage })))

const EmployeesPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.EmployeesPage })))
const DepartmentsPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.DepartmentsPage })))
const AttendancePage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.AttendancePage })))
const LeavePage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.LeavePage })))
const PayrollPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.PayrollPage })))
const PayslipsPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.PayslipsPage })))

const ProjectsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ProjectsPage })))
const TasksPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.TasksPage })))

const CampaignsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.CampaignsPage })))
const SegmentsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.SegmentsPage })))
const CampaignSendsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.CampaignSendsPage })))

const SettingsValuesPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.SettingsValuesPage })))
const SequencesPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.SequencesPage })))
const UsersPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.UsersPage })))
const RolesPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.RolesPage })))

function FullScreenLoader() {
  return (
    <div className="forest-grid flex min-h-screen flex-col items-center justify-center gap-4">
      <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gold text-lg font-extrabold text-forest">H</span>
      <div className="flex items-center gap-2 text-xs font-semibold text-white/50">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gold [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gold [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gold" />
        <span className="ml-1">Preparing your workspace</span>
      </div>
    </div>
  )
}

function Page({ children }) {
  return <Suspense fallback={<LoadingBlock />}>{children}</Suspense>
}

function ProtectedRoute() {
  const user = useAuth((state) => state.user)
  const loading = useAuth((state) => state.loading)
  const location = useLocation()

  if (loading) return <FullScreenLoader />
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  return <AppShell />
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [pathname])
  return null
}

export default function App() {
  const bootstrap = useAuth((state) => state.bootstrap)

  useEffect(() => {
    bootstrap()
  }, [bootstrap])

  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route element={<ProtectedRoute />}>
          <Route index element={<Page><Dashboard /></Page>} />
          <Route path="/assistant" element={<Page><Assistant /></Page>} />

          <Route path="/crm/companies" element={<Page><CompaniesPage /></Page>} />
          <Route path="/crm/contacts" element={<Page><ContactsPage /></Page>} />
          <Route path="/crm/leads" element={<Page><LeadsPage /></Page>} />
          <Route path="/crm/deals" element={<Page><DealsPage /></Page>} />
          <Route path="/crm/activities" element={<Page><ActivitiesPage /></Page>} />

          <Route path="/sales/orders" element={<Page><SalesOrdersPage /></Page>} />
          <Route path="/sales/customers" element={<Page><CustomersPage /></Page>} />
          <Route path="/sales/delivery-challans" element={<Page><DeliveryChallansPage /></Page>} />
          <Route path="/pos" element={<Page><Pos /></Page>} />

          <Route path="/inventory/products" element={<Page><ProductsPage /></Page>} />
          <Route path="/inventory/categories" element={<Page><CategoriesPage /></Page>} />
          <Route path="/inventory/stock" element={<Page><Stock /></Page>} />
          <Route path="/inventory/stock-moves" element={<Page><StockMovesPage /></Page>} />
          <Route path="/warehouse/warehouses" element={<Page><WarehousesPage /></Page>} />
          <Route path="/warehouse/bins" element={<Page><BinsPage /></Page>} />

          <Route path="/procurement/vendors" element={<Page><VendorsPage /></Page>} />
          <Route path="/procurement/requisitions" element={<Page><RequisitionsPage /></Page>} />
          <Route path="/procurement/purchase-orders" element={<Page><PurchaseOrdersPage /></Page>} />
          <Route path="/procurement/vendor-invoices" element={<Page><VendorInvoicesPage /></Page>} />

          <Route path="/finance/invoices" element={<Page><InvoicesPage /></Page>} />
          <Route path="/finance/payments" element={<Page><PaymentsPage /></Page>} />
          <Route path="/finance/accounts" element={<Page><AccountsPage /></Page>} />
          <Route path="/finance/journal-entries" element={<Page><JournalEntriesPage /></Page>} />
          <Route path="/finance/bank-accounts" element={<Page><BankAccountsPage /></Page>} />
          <Route path="/finance/reports" element={<Page><Reports /></Page>} />

          <Route path="/hr/employees" element={<Page><EmployeesPage /></Page>} />
          <Route path="/hr/departments" element={<Page><DepartmentsPage /></Page>} />
          <Route path="/hr/attendance" element={<Page><AttendancePage /></Page>} />
          <Route path="/hr/leave" element={<Page><LeavePage /></Page>} />
          <Route path="/hr/payroll" element={<Page><PayrollPage /></Page>} />
          <Route path="/hr/payslips" element={<Page><PayslipsPage /></Page>} />

          <Route path="/projects/projects" element={<Page><ProjectsPage /></Page>} />
          <Route path="/projects/tasks" element={<Page><TasksPage /></Page>} />
          <Route path="/support" element={<Page><Support /></Page>} />

          <Route path="/marketing/campaigns" element={<Page><CampaignsPage /></Page>} />
          <Route path="/marketing/segments" element={<Page><SegmentsPage /></Page>} />
          <Route path="/marketing/sends" element={<Page><CampaignSendsPage /></Page>} />

          <Route path="/settings" element={<Navigate to="/settings/values" replace />} />
          <Route path="/settings/values" element={<Page><SettingsValuesPage /></Page>} />
          <Route path="/settings/sequences" element={<Page><SequencesPage /></Page>} />
          <Route path="/settings/users" element={<Page><UsersPage /></Page>} />
          <Route path="/settings/roles" element={<Page><RolesPage /></Page>} />

          <Route path="*" element={<Page><NotFound /></Page>} />
        </Route>
      </Routes>
      <ToastHost />
    </>
  )
}
