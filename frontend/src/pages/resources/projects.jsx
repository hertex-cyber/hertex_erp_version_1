import { FolderKanban, ListChecks } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel } from '../../lib/format'

const PROJECT_STATUSES = ['planning', 'active', 'on_hold', 'completed', 'cancelled']
const TASK_STATUSES = ['todo', 'in_progress', 'done', 'blocked']
const PRIORITIES = ['low', 'medium', 'high', 'urgent']

export function ProjectsPage() {
  return (
    <ResourcePage
      eyebrow="Operations"
      title="Projects"
      description="Client work, budgets and delivery timelines in one view."
      endpoint="/projects/projects"
      permission="projects.project"
      createLabel="New project"
      searchPlaceholder="Search projects, codes…"
      filters={[{ name: 'status', label: 'All statuses', options: PROJECT_STATUSES }]}
      emptyIcon={FolderKanban}
      columns={[
        { key: 'name', label: 'Project', render: (row) => <Primary title={row.name} subtitle={`${row.code} · ${row.tasks?.length ?? 0} tasks`} /> },
        { key: 'client_name', label: 'Client' },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'budget', label: 'Budget', align: 'right', render: (row) => <Money value={row.budget} /> },
        { key: 'start_date', label: 'Starts', render: (row) => dateLabel(row.start_date) },
        { key: 'end_date', label: 'Ends', render: (row) => dateLabel(row.end_date) },
        { key: 'manager_id', label: 'Manager', render: (row) => <Ref lookup="users" id={row.manager_id} /> },
      ]}
      fields={[
        { name: 'name', label: 'Project name', required: true },
        { name: 'code', label: 'Project code', required: true },
        { name: 'client_name', label: 'Client' },
        { name: 'manager_id', label: 'Manager', type: 'reference', lookup: 'users' },
        { name: 'status', label: 'Status', type: 'select', options: PROJECT_STATUSES, default: 'planning' },
        { name: 'budget', label: 'Budget', type: 'number', default: 0 },
        { name: 'start_date', label: 'Start date', type: 'date', default: 'today' },
        { name: 'end_date', label: 'End date', type: 'date' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function TasksPage() {
  return (
    <ResourcePage
      eyebrow="Operations"
      title="Tasks"
      description="Delivery granularity: owners, effort, billing and due dates."
      endpoint="/projects/tasks"
      permission="projects.task"
      createLabel="New task"
      searchPlaceholder="Search tasks…"
      filters={[
        { name: 'status', label: 'All statuses', options: TASK_STATUSES },
        { name: 'priority', label: 'All priorities', options: PRIORITIES },
      ]}
      emptyIcon={ListChecks}
      columns={[
        { key: 'title', label: 'Task', render: (row) => <Primary title={row.title} subtitle={row.description || 'No description'} /> },
        { key: 'project_id', label: 'Project', render: (row) => <Ref lookup="projects" id={row.project_id} /> },
        { key: 'assignee_id', label: 'Assignee', render: (row) => <Ref lookup="users" id={row.assignee_id} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'priority', label: 'Priority', render: (row) => <TypeBadge value={row.priority} /> },
        { key: 'due_date', label: 'Due', render: (row) => dateLabel(row.due_date) },
        { key: 'is_billable', label: 'Billable', render: (row) => <Status value={row.is_billable ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'project_id', label: 'Project', type: 'reference', lookup: 'projects', required: true },
        { name: 'title', label: 'Task title', required: true },
        { name: 'assignee_id', label: 'Assignee', type: 'reference', lookup: 'users' },
        { name: 'status', label: 'Status', type: 'select', options: TASK_STATUSES, default: 'todo' },
        { name: 'priority', label: 'Priority', type: 'select', options: PRIORITIES, default: 'medium' },
        { name: 'due_date', label: 'Due date', type: 'date' },
        { name: 'estimated_hours', label: 'Estimated hours', type: 'number', default: 0 },
        { name: 'actual_hours', label: 'Actual hours', type: 'number', default: 0 },
        { name: 'billable_rate', label: 'Billable rate', type: 'number', default: 0 },
        { name: 'budget_amount', label: 'Budget amount', type: 'number', default: 0 },
        { name: 'is_billable', label: 'Billable', type: 'checkbox', default: true },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}
