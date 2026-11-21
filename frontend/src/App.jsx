import { lazy, Suspense, useEffect } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import AppShell from './components/AppShell'
import BrandLogo from './components/BrandLogo'
import { LoadingBlock, ToastHost } from './components/ui'
import { describePath } from './lib/nav'
import { useAuth } from './store/auth'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage } from './pages/Auth'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const FinanceDashboard = lazy(() => import('./pages/FinanceDashboard'))
const Stock = lazy(() => import('./pages/Stock'))
const Reports = lazy(() => import('./pages/Reports'))
const Pos = lazy(() => import('./pages/Pos'))
const Support = lazy(() => import('./pages/Support'))
const Assistant = lazy(() => import('./pages/Assistant'))
const Security = lazy(() => import('./pages/Security'))
const NotFound = lazy(() => import('./pages/NotFound'))

const CompaniesPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.CompaniesPage })))
const ContactsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.ContactsPage })))
const LeadsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.LeadsPage })))
const DealsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.DealsPage })))
const ActivitiesPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.ActivitiesPage })))
const InboxPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.InboxPage })))
const CallsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.CallsPage })))
const CallAssessmentsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.CallAssessmentsPage })))
const SocialAccountsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.SocialAccountsPage })))
const SocialPostsPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.SocialPostsPage })))
const PipelineReportPage = lazy(() => import('./pages/resources/crm').then((module) => ({ default: module.PipelineReportPage })))

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

const InvoicesPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.InvoicesPage })))
const PaymentsPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.PaymentsPage })))
const AccountsPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.AccountsPage })))
const AccountGroupsPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.AccountGroupsPage })))
const JournalEntriesPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.JournalEntriesPage })))
const PeriodsPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.PeriodsPage })))
const BankAccountsPage = lazy(() => import('./pages/finance/Registers').then((module) => ({ default: module.BankAccountsPage })))
const VendorPaymentsPage = lazy(() => import('./pages/finance/VendorPaymentsPage'))
const BankReconciliationPage = lazy(() => import('./pages/finance/BankReconciliationPage'))
const GSTPage = lazy(() => import('./pages/finance/GSTPage'))
const ApprovalsPage = lazy(() => import('./pages/finance/ApprovalsPage'))
const FixedAssetsPage = lazy(() => import('./pages/finance/FixedAssetsPage'))
const BankFeedsPage = lazy(() =>
  import('./pages/finance/CompliancePages').then((module) => ({ default: module.BankFeedsPage })),
)
const ControlPlanePage = lazy(() =>
  import('./pages/finance/CompliancePages').then((module) => ({ default: module.ControlPlanePage })),
)
const StatutoryPage = lazy(() =>
  import('./pages/finance/CompliancePages').then((module) => ({ default: module.StatutoryPage })),
)
const ConsolidationPage = lazy(() =>
  import('./pages/finance/DimensionsConsolidationPages').then((module) => ({ default: module.ConsolidationPage })),
)
const DimensionsPage = lazy(() =>
  import('./pages/finance/DimensionsConsolidationPages').then((module) => ({ default: module.DimensionsPage })),
)
const FinanceBudgetsPage = lazy(() =>
  import('./pages/finance/DimensionsConsolidationPages').then((module) => ({ default: module.FinanceBudgetsPage })),
)
const ExtendedReportsPage = lazy(() => import('./pages/finance/ExtendedReportsPage'))
const ExternalIntegrationsPage = lazy(() => import('./pages/finance/ExternalIntegrationsPage'))
const OcrInboxPage = lazy(() => import('./pages/finance/OcrInboxPage'))

const EmployeesPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.EmployeesPage })))
const DepartmentsPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.DepartmentsPage })))
const AttendancePage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.AttendancePage })))
const LeavePage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.LeavePage })))
const PayrollPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.PayrollPage })))
const PayslipsPage = lazy(() => import('./pages/resources/hr').then((module) => ({ default: module.PayslipsPage })))

const ProjectsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ProjectsPage })))
const WorkItemsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.WorkItemsPage })))
const TasksPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.TasksPage })))
const BoardsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BoardsPage })))
const BoardColumnsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BoardColumnsPage })))
const BoardPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BoardPage })))
const SprintsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.SprintsPage })))
const MilestonesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.MilestonesPage })))
const DependenciesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.DependenciesPage })))
const PortfoliosPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.PortfoliosPage })))
const ProgramsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ProgramsPage })))
const PhasesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.PhasesPage })))
const TimeEntriesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.TimeEntriesPage })))
const TimesheetsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.TimesheetsPage })))
const ExpensesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ExpensesPage })))
const CostEntriesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.CostEntriesPage })))
const BillingRunsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BillingRunsPage })))
const BudgetsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BudgetsPage })))
const ResourceRolesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ResourceRolesPage })))
const BookingsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.BookingsPage })))
const CapacityPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.CapacityPage })))
const WorkloadPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.WorkloadPage })))
const RisksPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.RisksPage })))
const IssuesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.IssuesPage })))
const ChangeRequestsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ChangeRequestsPage })))
const DecisionsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.DecisionsPage })))
const StatusUpdatesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.StatusUpdatesPage })))
const GoalsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.GoalsPage })))
const AiSignalsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.AiSignalsPage })))
const AiActionsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.AiActionsPage })))
const AutomationRulesPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.AutomationRulesPage })))
const AutomationRunsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.AutomationRunsPage })))
const OutboxPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.OutboxPage })))
const ReportsPage = lazy(() => import('./pages/resources/projects').then((module) => ({ default: module.ReportsPage })))

const ProjectDetailPage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.ProjectDetailPage })))
const BacklogPage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.BacklogPage })))
const GanttPage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.GanttPage })))
const ImportsPage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.ImportsPage })))
const IntakePage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.IntakePage })))
const NotificationsPage = lazy(() => import('./pages/resources/projects-workspace').then((module) => ({ default: module.NotificationsPage })))

const LabelsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.LabelsPage })))
const CustomFieldsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.CustomFieldsPage })))
const FieldValuesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.FieldValuesPage })))
const WorkflowsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.WorkflowsPage })))
const TransitionsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.TransitionsPage })))
const TemplatesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.TemplatesPage })))
const ApprovalsRegisterPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.ApprovalsRegisterPage })))
const BaselinesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.BaselinesPage })))
const BaselineSnapshotsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.BaselineSnapshotsPage })))
const ReleasesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.ReleasesPage })))
const WorkItemLinksPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.WorkItemLinksPage })))
const RetrospectivesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.RetrospectivesPage })))
const TimesheetEntriesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.TimesheetEntriesPage })))
const BillingLinesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.BillingLinesPage })))
const InvoiceLinksPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.InvoiceLinksPage })))
const BudgetRevisionsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.BudgetRevisionsPage })))
const EmployeeSkillsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.EmployeeSkillsPage })))
const CapacityCalendarsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.CapacityCalendarsPage })))
const WorkloadSnapshotsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.WorkloadSnapshotsPage })))
const IntegrationsPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.IntegrationsPage })))
const ImportBatchesPage = lazy(() => import('./pages/resources/projects-settings').then((module) => ({ default: module.ImportBatchesPage })))

const CommentsPage = lazy(() => import('./pages/resources/projects-collab').then((module) => ({ default: module.CommentsPage })))
const AttachmentsPage = lazy(() => import('./pages/resources/projects-collab').then((module) => ({ default: module.AttachmentsPage })))
const ActivityPage = lazy(() => import('./pages/resources/projects-collab').then((module) => ({ default: module.ActivityPage })))

const CampaignsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.CampaignsPage })))
const SegmentsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.SegmentsPage })))
const CampaignSendsPage = lazy(() => import('./pages/resources/marketing').then((module) => ({ default: module.CampaignSendsPage })))

const SettingsHubPage = lazy(() => import('./pages/settings/SettingsHubPage'))
const OrganisationPage = lazy(() => import('./pages/settings/OrganisationPage'))
const LocalisationPage = lazy(() => import('./pages/settings/LocalisationPage'))
const ModulesPage = lazy(() => import('./pages/settings/ModulesPage'))
const SettingsValuesPage = lazy(() => import('./pages/settings/ValuesPage'))
const SequencesPage = lazy(() => import('./pages/settings/NumberingPage'))
const NumberingGapsPage = lazy(() => import('./pages/settings/GapsPage'))
const NumberingBlocksPage = lazy(() => import('./pages/settings/BlocksPage'))
const SecretsPage = lazy(() => import('./pages/settings/SecretsPage'))
const SettingsHistoryPage = lazy(() => import('./pages/settings/HistoryPage'))
const UsersPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.UsersPage })))
const RolesPage = lazy(() => import('./pages/resources/settings').then((module) => ({ default: module.RolesPage })))

function FullScreenLoader() {
  return (
    <div className="forest-grid flex min-h-screen flex-col items-center justify-center gap-4">
      <BrandLogo className="h-12 drop-shadow-[0_8px_24px_rgba(255,105,0,0.35)]" />
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

function AccessDenied() {
  return (
    <div className="forest-grid flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center" data-testid="access-denied">
      <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gold text-forest"><ShieldAlert size={24} /></span>
      <h1 className="display text-2xl font-semibold text-white">Access denied</h1>
      <p className="max-w-md text-sm text-white/60">Your role does not have access to this module. Ask an administrator if you need it enabled.</p>
      <Link to="/" className="mt-2 rounded-xl bg-gold px-4 py-2 text-xs font-bold text-forest">Back to command centre</Link>
    </div>
  )
}

function ProtectedRoute() {
  const user = useAuth((state) => state.user)
  const loading = useAuth((state) => state.loading)
  const canView = useAuth().canView
  const location = useLocation()

  if (loading) return <FullScreenLoader />
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (!canView(describePath(location.pathname))) return <AccessDenied />
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
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        <Route element={<ProtectedRoute />}>
          <Route index element={<Page><Dashboard /></Page>} />
          <Route path="/assistant" element={<Page><Assistant /></Page>} />

          <Route path="/crm/companies" element={<Page><CompaniesPage /></Page>} />
          <Route path="/crm/contacts" element={<Page><ContactsPage /></Page>} />
          <Route path="/crm/leads" element={<Page><LeadsPage /></Page>} />
          <Route path="/crm/deals" element={<Page><DealsPage /></Page>} />
          <Route path="/crm/activities" element={<Page><ActivitiesPage /></Page>} />
          <Route path="/crm/inbox" element={<Page><InboxPage /></Page>} />
          <Route path="/crm/calls" element={<Page><CallsPage /></Page>} />
          <Route path="/crm/call-assessments" element={<Page><CallAssessmentsPage /></Page>} />
          <Route path="/crm/social/accounts" element={<Page><SocialAccountsPage /></Page>} />
          <Route path="/crm/social/posts" element={<Page><SocialPostsPage /></Page>} />
          <Route path="/crm/pipeline-report" element={<Page><PipelineReportPage /></Page>} />

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
          <Route path="/procurement/ocr-inbox" element={<Navigate to="/finance/ocr-inbox" replace />} />

          <Route path="/finance" element={<Page><FinanceDashboard /></Page>} />
          <Route path="/finance/invoices" element={<Page><InvoicesPage /></Page>} />
          <Route path="/finance/payments" element={<Page><PaymentsPage /></Page>} />
          <Route path="/finance/vendor-payments" element={<Page><VendorPaymentsPage /></Page>} />
          <Route path="/finance/ocr-inbox" element={<Page><OcrInboxPage /></Page>} />
          <Route path="/finance/approvals" element={<Page><ApprovalsPage /></Page>} />
          <Route path="/finance/bank-reconciliation" element={<Page><BankReconciliationPage /></Page>} />
          <Route path="/finance/gst" element={<Page><GSTPage /></Page>} />
          <Route path="/finance/accounts" element={<Page><AccountsPage /></Page>} />
          <Route path="/finance/account-groups" element={<Page><AccountGroupsPage /></Page>} />
          <Route path="/finance/journal-entries" element={<Page><JournalEntriesPage /></Page>} />
          <Route path="/finance/periods" element={<Page><PeriodsPage /></Page>} />
          <Route path="/finance/bank-accounts" element={<Page><BankAccountsPage /></Page>} />
          <Route path="/finance/reports" element={<Page><Reports /></Page>} />
          <Route path="/finance/reports/extended" element={<Page><ExtendedReportsPage /></Page>} />
          <Route path="/finance/assets" element={<Page><FixedAssetsPage /></Page>} />
          <Route path="/finance/control-plane" element={<Page><ControlPlanePage /></Page>} />
          <Route path="/finance/statutory" element={<Page><StatutoryPage /></Page>} />
          <Route path="/finance/bank-feeds" element={<Page><BankFeedsPage /></Page>} />
          <Route path="/finance/external-integrations" element={<Page><ExternalIntegrationsPage /></Page>} />
          <Route path="/finance/dimensions" element={<Page><DimensionsPage /></Page>} />
          <Route path="/finance/consolidation" element={<Page><ConsolidationPage /></Page>} />
          <Route path="/finance/budgets" element={<Page><FinanceBudgetsPage /></Page>} />

          <Route path="/hr/employees" element={<Page><EmployeesPage /></Page>} />
          <Route path="/hr/departments" element={<Page><DepartmentsPage /></Page>} />
          <Route path="/hr/attendance" element={<Page><AttendancePage /></Page>} />
          <Route path="/hr/leave" element={<Page><LeavePage /></Page>} />
          <Route path="/hr/payroll" element={<Page><PayrollPage /></Page>} />
          <Route path="/hr/payslips" element={<Page><PayslipsPage /></Page>} />

          <Route path="/projects" element={<Navigate to="/projects/projects" replace />} />
          <Route path="/projects/projects" element={<Page><ProjectsPage /></Page>} />
          <Route path="/projects/projects/:id" element={<Page><ProjectDetailPage /></Page>} />
          <Route path="/projects/work-items" element={<Page><WorkItemsPage /></Page>} />
          <Route path="/projects/tasks" element={<Page><TasksPage /></Page>} />
          <Route path="/projects/board" element={<Page><BoardPage /></Page>} />
          <Route path="/projects/boards" element={<Page><BoardsPage /></Page>} />
          <Route path="/projects/board-columns" element={<Page><BoardColumnsPage /></Page>} />
          <Route path="/projects/sprints" element={<Page><SprintsPage /></Page>} />
          <Route path="/projects/milestones" element={<Page><MilestonesPage /></Page>} />
          <Route path="/projects/dependencies" element={<Page><DependenciesPage /></Page>} />
          <Route path="/projects/reports" element={<Page><ReportsPage /></Page>} />

          <Route path="/projects/backlog" element={<Page><BacklogPage /></Page>} />
          <Route path="/projects/gantt" element={<Page><GanttPage /></Page>} />
          <Route path="/projects/intake" element={<Page><IntakePage /></Page>} />
          <Route path="/projects/imports" element={<Page><ImportsPage /></Page>} />
          <Route path="/projects/notifications" element={<Page><NotificationsPage /></Page>} />

          <Route path="/projects/portfolios" element={<Page><PortfoliosPage /></Page>} />
          <Route path="/projects/programs" element={<Page><ProgramsPage /></Page>} />
          <Route path="/projects/phases" element={<Page><PhasesPage /></Page>} />
          <Route path="/projects/goals" element={<Page><GoalsPage /></Page>} />
          <Route path="/projects/status-updates" element={<Page><StatusUpdatesPage /></Page>} />
          <Route path="/projects/decisions" element={<Page><DecisionsPage /></Page>} />
          <Route path="/projects/work-item-links" element={<Page><WorkItemLinksPage /></Page>} />
          <Route path="/projects/releases" element={<Page><ReleasesPage /></Page>} />
          <Route path="/projects/retrospectives" element={<Page><RetrospectivesPage /></Page>} />
          <Route path="/projects/baselines" element={<Page><BaselinesPage /></Page>} />
          <Route path="/projects/baseline-snapshots" element={<Page><BaselineSnapshotsPage /></Page>} />

          <Route path="/projects/time-entries" element={<Page><TimeEntriesPage /></Page>} />
          <Route path="/projects/timesheets" element={<Page><TimesheetsPage /></Page>} />
          <Route path="/projects/timesheet-entries" element={<Page><TimesheetEntriesPage /></Page>} />
          <Route path="/projects/expenses" element={<Page><ExpensesPage /></Page>} />
          <Route path="/projects/cost-entries" element={<Page><CostEntriesPage /></Page>} />
          <Route path="/projects/billing-runs" element={<Page><BillingRunsPage /></Page>} />
          <Route path="/projects/billing-lines" element={<Page><BillingLinesPage /></Page>} />
          <Route path="/projects/invoice-links" element={<Page><InvoiceLinksPage /></Page>} />
          <Route path="/projects/budgets" element={<Page><BudgetsPage /></Page>} />
          <Route path="/projects/budget-revisions" element={<Page><BudgetRevisionsPage /></Page>} />

          <Route path="/projects/resource-roles" element={<Page><ResourceRolesPage /></Page>} />
          <Route path="/projects/bookings" element={<Page><BookingsPage /></Page>} />
          <Route path="/projects/capacity" element={<Page><CapacityPage /></Page>} />
          <Route path="/projects/capacity-calendars" element={<Page><CapacityCalendarsPage /></Page>} />
          <Route path="/projects/employee-skills" element={<Page><EmployeeSkillsPage /></Page>} />
          <Route path="/projects/workload" element={<Page><WorkloadPage /></Page>} />
          <Route path="/projects/workload-snapshots" element={<Page><WorkloadSnapshotsPage /></Page>} />

          <Route path="/projects/risks" element={<Page><RisksPage /></Page>} />
          <Route path="/projects/issues" element={<Page><IssuesPage /></Page>} />
          <Route path="/projects/change-requests" element={<Page><ChangeRequestsPage /></Page>} />
          <Route path="/projects/approvals" element={<Page><ApprovalsRegisterPage /></Page>} />

          <Route path="/projects/labels" element={<Page><LabelsPage /></Page>} />
          <Route path="/projects/custom-fields" element={<Page><CustomFieldsPage /></Page>} />
          <Route path="/projects/field-values" element={<Page><FieldValuesPage /></Page>} />
          <Route path="/projects/workflows" element={<Page><WorkflowsPage /></Page>} />
          <Route path="/projects/transitions" element={<Page><TransitionsPage /></Page>} />
          <Route path="/projects/templates" element={<Page><TemplatesPage /></Page>} />
          <Route path="/projects/integrations" element={<Page><IntegrationsPage /></Page>} />
          <Route path="/projects/import-batches" element={<Page><ImportBatchesPage /></Page>} />

          <Route path="/projects/comments" element={<Page><CommentsPage /></Page>} />
          <Route path="/projects/attachments" element={<Page><AttachmentsPage /></Page>} />
          <Route path="/projects/activity" element={<Page><ActivityPage /></Page>} />

          <Route path="/projects/ai-signals" element={<Page><AiSignalsPage /></Page>} />
          <Route path="/projects/ai-actions" element={<Page><AiActionsPage /></Page>} />
          <Route path="/projects/automation-rules" element={<Page><AutomationRulesPage /></Page>} />
          <Route path="/projects/automation-runs" element={<Page><AutomationRunsPage /></Page>} />
          <Route path="/projects/outbox" element={<Page><OutboxPage /></Page>} />
          <Route path="/support" element={<Page><Support /></Page>} />

          <Route path="/marketing/campaigns" element={<Page><CampaignsPage /></Page>} />
          <Route path="/marketing/segments" element={<Page><SegmentsPage /></Page>} />
          <Route path="/marketing/sends" element={<Page><CampaignSendsPage /></Page>} />

          <Route path="/settings" element={<Page><SettingsHubPage /></Page>} />
          <Route path="/settings/organisation" element={<Page><OrganisationPage /></Page>} />
          <Route path="/settings/localisation" element={<Page><LocalisationPage /></Page>} />
          <Route path="/settings/modules" element={<Page><ModulesPage /></Page>} />
          <Route path="/settings/values" element={<Page><SettingsValuesPage /></Page>} />
          <Route path="/settings/numbering" element={<Page><SequencesPage /></Page>} />
          <Route path="/settings/sequences" element={<Navigate to="/settings/numbering" replace />} />
          <Route path="/settings/numbering/gaps" element={<Page><NumberingGapsPage /></Page>} />
          <Route path="/settings/numbering/blocks" element={<Page><NumberingBlocksPage /></Page>} />
          <Route path="/settings/secrets" element={<Page><SecretsPage /></Page>} />
          <Route path="/settings/history" element={<Page><SettingsHistoryPage /></Page>} />
          <Route path="/settings/users" element={<Page><UsersPage /></Page>} />
          <Route path="/settings/roles" element={<Page><RolesPage /></Page>} />
          <Route path="/settings/security" element={<Page><Security /></Page>} />

          <Route path="*" element={<Page><NotFound /></Page>} />
        </Route>
      </Routes>
      <ToastHost />
    </>
  )
}
