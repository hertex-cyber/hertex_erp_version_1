import { CalendarCheck, CalendarDays, BadgeCheck, UserRound, Wallet } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { api, apiErrorMessage } from '../../lib/api'
import { Money, Primary, Qty, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'intern']
const EMPLOYEE_STATUSES = ['active', 'on_leave', 'probation', 'terminated']
const ATTENDANCE_STATUSES = ['present', 'absent', 'late', 'half_day', 'leave']
const LEAVE_TYPES = ['casual', 'sick', 'earned', 'unpaid', 'maternity', 'paternity']

export function EmployeesPage() {
  return (
    <ResourcePage
      eyebrow="People"
      title="Employees"
      description="Your team, their roles, compensation and employment status."
      endpoint="/hr/employees"
      permission="hr.employee"
      createLabel="New employee"
      searchPlaceholder="Search name, code, email…"
      filters={[
        { name: 'status', label: 'All statuses', options: EMPLOYEE_STATUSES },
        { name: 'employment_type', label: 'All types', options: EMPLOYMENT_TYPES },
      ]}
      emptyIcon={UserRound}
      columns={[
        { key: 'first_name', label: 'Employee', render: (row) => <Primary title={`${row.first_name} ${row.last_name ?? ''}`.trim()} subtitle={row.employee_code} /> },
        { key: 'designation', label: 'Designation' },
        { key: 'department_id', label: 'Department', render: (row) => <Ref lookup="departments" id={row.department_id} /> },
        { key: 'employment_type', label: 'Type', render: (row) => <TypeBadge value={row.employment_type} /> },
        { key: 'date_of_joining', label: 'Joined', render: (row) => dateLabel(row.date_of_joining) },
        { key: 'salary', label: 'Salary', align: 'right', render: (row) => <Money value={row.salary} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      ]}
      fields={[
        { name: 'employee_code', label: 'Employee code', required: true },
        { name: 'first_name', label: 'First name', required: true },
        { name: 'last_name', label: 'Last name' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'designation', label: 'Designation' },
        { name: 'department_id', label: 'Department', type: 'reference', lookup: 'departments' },
        { name: 'employment_type', label: 'Employment type', type: 'select', options: EMPLOYMENT_TYPES, default: 'full_time' },
        { name: 'date_of_joining', label: 'Date of joining', type: 'date', default: 'today' },
        { name: 'date_of_birth', label: 'Date of birth', type: 'date' },
        { name: 'salary', label: 'Monthly salary', type: 'number', default: 0 },
        { name: 'bank_account', label: 'Bank account' },
        { name: 'status', label: 'Status', type: 'select', options: EMPLOYEE_STATUSES, default: 'active' },
        { name: 'address', label: 'Address', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function DepartmentsPage() {
  return (
    <ResourcePage
      eyebrow="People"
      title="Departments"
      description="Teams and cost centres that organise the org chart."
      endpoint="/hr/departments"
      permission="hr.department"
      createLabel="New department"
      searchPlaceholder="Search departments…"
      columns={[
        { key: 'name', label: 'Department', render: (row) => <Primary title={row.name} subtitle={row.description || 'No description'} /> },
        { key: 'created_at', label: 'Created', render: (row) => dateLabel(row.created_at) },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Department name', required: true, colSpan: 2 },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function AttendancePage() {
  return (
    <ResourcePage
      eyebrow="People"
      title="Attendance"
      description="Daily check-ins, shifts and exceptions across the team."
      endpoint="/hr/attendance"
      permission="hr.attendance"
      createLabel="Mark attendance"
      filters={[{ name: 'status', label: 'All statuses', options: ATTENDANCE_STATUSES }]}
      emptyIcon={CalendarCheck}
      columns={[
        { key: 'employee_id', label: 'Employee', render: (row) => <Ref lookup="employees" id={row.employee_id} /> },
        { key: 'work_date', label: 'Date', render: (row) => dateLabel(row.work_date) },
        { key: 'check_in', label: 'Check in', render: (row) => row.check_in ? String(row.check_in).slice(0, 5) : '—' },
        { key: 'check_out', label: 'Check out', render: (row) => row.check_out ? String(row.check_out).slice(0, 5) : '—' },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'notes', label: 'Notes' },
      ]}
      fields={[
        { name: 'employee_id', label: 'Employee', type: 'reference', lookup: 'employees', required: true },
        { name: 'work_date', label: 'Work date', type: 'date', default: 'today', required: true },
        { name: 'check_in', label: 'Check in', type: 'time' },
        { name: 'check_out', label: 'Check out', type: 'time' },
        { name: 'status', label: 'Status', type: 'select', options: ATTENDANCE_STATUSES, default: 'present', required: true },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function LeavePage() {
  const can = useAuth((state) => state.can)

  const approve = async (row, { reload }) => {
    try {
      await api.post(`/hr/leave-requests/${row.id}/approve`)
      toast.success('Leave approved', 'The employee’s leave request was approved.')
      reload()
    } catch (error) {
      toast.error('Could not approve leave', apiErrorMessage(error))
    }
  }

  return (
    <ResourcePage
      eyebrow="People"
      title="Leave requests"
      description="Time-off requests with approval status and coverage."
      endpoint="/hr/leave-requests"
      permission="hr.leaverequest"
      createLabel="New leave request"
      filters={[
        { name: 'status', label: 'All statuses', options: ['pending', 'approved', 'rejected'] },
        { name: 'leave_type', label: 'All leave types', options: LEAVE_TYPES },
      ]}
      emptyIcon={CalendarDays}
      columns={[
        { key: 'employee_id', label: 'Employee', render: (row) => <Ref lookup="employees" id={row.employee_id} /> },
        { key: 'leave_type', label: 'Type', render: (row) => <TypeBadge value={row.leave_type} /> },
        { key: 'start_date', label: 'From', render: (row) => dateLabel(row.start_date) },
        { key: 'end_date', label: 'To', render: (row) => dateLabel(row.end_date) },
        { key: 'days', label: 'Days', align: 'right', render: (row) => <Qty value={row.days} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      ]}
      rowActions={[
        {
          label: 'Approve leave',
          icon: BadgeCheck,
          tone: 'positive',
          show: (row) => can('hr.leaverequest.update') && row.status === 'pending',
          onClick: approve,
        },
      ]}
      fields={[
        { name: 'employee_id', label: 'Employee', type: 'reference', lookup: 'employees', required: true },
        { name: 'leave_type', label: 'Leave type', type: 'select', options: LEAVE_TYPES, default: 'casual' },
        { name: 'start_date', label: 'Start date', type: 'date', default: 'today', required: true },
        { name: 'end_date', label: 'End date', type: 'date', default: 'today', required: true },
        { name: 'days', label: 'Days', type: 'number', default: 1 },
        { name: 'status', label: 'Status', type: 'select', options: ['pending', 'approved', 'rejected'], default: 'pending' },
        { name: 'reason', label: 'Reason', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function PayrollPage() {
  const can = useAuth((state) => state.can)

  const process = async (row, { reload }) => {
    try {
      await api.post(`/hr/payroll-runs/${row.id}/process`)
      toast.success('Payroll processed', `Payslips were generated for ${row.period}.`)
      reload()
    } catch (error) {
      toast.error('Could not process payroll', apiErrorMessage(error))
    }
  }

  return (
    <ResourcePage
      eyebrow="People"
      title="Payroll"
      description="Monthly payroll runs with ledger accruals. PF, ESI and TDS formulas are provisional; validate statutory rules before live payroll."
      endpoint="/hr/payroll-runs"
      permission="hr.payrollrun"
      createLabel="New payroll run"
      canEdit={false}
      filters={[{ name: 'status', label: 'All statuses', options: ['draft', 'processed'] }]}
      emptyIcon={Wallet}
      columns={[
        { key: 'period', label: 'Period', render: (row) => <Primary title={row.period} subtitle={row.status === 'processed' ? dateLabel(row.processed_at) : 'Not processed'} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'total_gross', label: 'Gross', align: 'right', render: (row) => <Money value={row.total_gross} /> },
        { key: 'total_deductions', label: 'Deductions', align: 'right', render: (row) => <Money value={row.total_deductions} /> },
        { key: 'total_net', label: 'Net pay', align: 'right', render: (row) => <Money value={row.total_net} /> },
        { key: 'journal_entry_id', label: 'Ledger', render: (row) => row.journal_entry_id ? <span className="font-mono text-xs" title={row.journal_entry_id}>{row.journal_entry_id.slice(0, 8)}</span> : <TypeBadge value="not posted" /> },
      ]}
      rowActions={[
        {
          label: 'Process payroll',
          icon: BadgeCheck,
          tone: 'positive',
          show: (row) => can('hr.payrollrun.update') && row.status === 'draft',
          onClick: process,
        },
      ]}
      fields={[
        { name: 'period', label: 'Period (YYYY-MM)', required: true, placeholder: '2026-11' },
      ]}
    />
  )
}

export function PayslipsPage() {
  return (
    <ResourcePage
      eyebrow="People"
      title="Payslips"
      description="Generated payslips with statutory deductions and net pay."
      endpoint="/hr/payslips"
      permission="hr.payslip"
      readPermission="hr.payslip.read"
      canCreate={false}
      canEdit={false}
      canDelete={false}
      emptyIcon={Wallet}
      emptyTitle="No payslips generated"
      emptyDescription="Process a payroll run to generate payslips."
      columns={[
        { key: 'employee_id', label: 'Employee', render: (row) => <Ref lookup="employees" id={row.employee_id} /> },
        { key: 'gross', label: 'Gross', align: 'right', render: (row) => <Money value={row.gross} /> },
        { key: 'pf', label: 'PF', align: 'right', render: (row) => <Money value={row.pf} /> },
        { key: 'esi', label: 'ESI', align: 'right', render: (row) => <Money value={row.esi} /> },
        { key: 'tds', label: 'TDS', align: 'right', render: (row) => <Money value={row.tds} /> },
        { key: 'net', label: 'Net', align: 'right', render: (row) => <Money value={row.net} /> },
        { key: 'created_at', label: 'Created', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[]}
    />
  )
}
