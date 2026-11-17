import { KeyRound, Settings, ShieldCheck, Users } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Primary, Ref, Status } from '../../components/cells'
import { dateLabel, dateTimeLabel } from '../../lib/format'

export function SettingsValuesPage() {
  return (
    <ResourcePage
      eyebrow="Workspace"
      title="Settings"
      description="Workspace-level configuration values, grouped by category."
      endpoint="/settings/values"
      permission="settings.setting"
      createLabel="New setting"
      searchPlaceholder="Search keys, categories…"
      emptyIcon={Settings}
      columns={[
        { key: 'key', label: 'Key', render: (row) => <Primary title={row.key} subtitle={row.description || 'No description'} /> },
        { key: 'category', label: 'Category' },
        { key: 'value', label: 'Value', render: (row) => <code className="rounded bg-surface-2 px-2 py-1 text-[10px] text-ink-soft">{JSON.stringify(row.value ?? {}).slice(0, 70)}</code> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
        { key: 'created_at', label: 'Updated', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'key', label: 'Setting key', required: true },
        { name: 'category', label: 'Category' },
        { name: 'value', label: 'Value (JSON)', type: 'json', default: '{}', colSpan: 2 },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function SequencesPage() {
  return (
    <ResourcePage
      eyebrow="Workspace"
      title="Number sequences"
      description="Control document prefixes and next numbers for every module."
      endpoint="/settings/sequences"
      permission="settings.sequence"
      createLabel="New sequence"
      searchPlaceholder="Search sequences…"
      emptyIcon={KeyRound}
      columns={[
        { key: 'key', label: 'Sequence', render: (row) => <Primary title={row.key} subtitle={row.prefix} /> },
        { key: 'next_number', label: 'Next number', align: 'right' },
        { key: 'padding', label: 'Padding', align: 'right' },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'key', label: 'Sequence key', required: true },
        { name: 'prefix', label: 'Prefix', required: true },
        { name: 'next_number', label: 'Next number', type: 'number', default: 1 },
        { name: 'padding', label: 'Padding', type: 'number', default: 5 },
      ]}
    />
  )
}

export function UsersPage() {
  return (
    <ResourcePage
      eyebrow="Workspace"
      title="Team"
      description="People with access to this workspace, their roles and status."
      endpoint="/users"
      permission="system.user"
      readPermission="system.user.manage"
      createPermission="system.user.manage"
      updatePermission="system.user.manage"
      deletePermission="system.user.manage"
      createLabel="Invite user"
      searchPlaceholder="Search name, email…"
      emptyIcon={Users}
      columns={[
        { key: 'full_name', label: 'Person', render: (row) => <Primary title={row.full_name} subtitle={row.email} /> },
        {
          key: 'roles',
          label: 'Roles',
          render: (row) => (
            <div className="flex flex-wrap gap-1">
              {(row.roles ?? []).map((role) => (
                <span key={role.id} className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-bold text-primary">{role.name}</span>
              ))}
              {row.is_superuser && <span className="rounded-full bg-gold-soft px-2 py-0.5 text-[10px] font-bold text-gold">Super admin</span>}
            </div>
          ),
        },
        { key: 'last_login_at', label: 'Last login', render: (row) => dateTimeLabel(row.last_login_at) },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      editFields={[
        { name: 'full_name', label: 'Full name' },
        { name: 'phone', label: 'Phone' },
        { name: 'avatar_url', label: 'Avatar URL', colSpan: 2 },
        { name: 'role_ids', label: 'Roles', type: 'multiselect', lookup: 'roles', colSpan: 2 },
        { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
      ]}
      fields={[
        { name: 'full_name', label: 'Full name', required: true },
        { name: 'email', label: 'Email', type: 'email', required: true },
        { name: 'password', label: 'Temporary password', type: 'password', required: true, help: 'Minimum 8 characters. Share securely with the new user.' },
        { name: 'phone', label: 'Phone' },
        { name: 'role_ids', label: 'Roles', type: 'multiselect', lookup: 'roles', colSpan: 2 },
        { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
      ]}
    />
  )
}

export function RolesPage() {
  return (
    <ResourcePage
      eyebrow="Workspace"
      title="Roles & access"
      description="Permission bundles that shape what each teammate can see and do."
      endpoint="/roles"
      permission="system.role"
      readPermission="system.role.manage"
      createPermission="system.role.manage"
      updatePermission="system.role.manage"
      deletePermission="system.role.manage"
      createLabel="New role"
      searchPlaceholder="Search roles…"
      emptyIcon={ShieldCheck}
      columns={[
        { key: 'name', label: 'Role', render: (row) => <Primary title={row.name} subtitle={row.description || 'No description'} /> },
        { key: 'slug', label: 'Slug' },
        { key: 'permissions', label: 'Permissions', align: 'right', render: (row) => <span className="font-bold tabular-nums text-ink">{row.permissions?.length ?? 0}</span> },
        { key: 'approval_limit', label: 'Approval limit', render: (row) => (row.approval_limit ? `₹${row.approval_limit}` : '—') },
        { key: 'is_system', label: 'Type', render: (row) => <Status value={row.is_system ? 'system' : 'custom'} /> },
      ]}
      editFields={[
        { name: 'name', label: 'Role name' },
        { name: 'description', label: 'Description' },
        { name: 'approval_limit', label: 'Approval limit', type: 'number' },
        { name: 'permission_ids', label: 'Permissions', type: 'multiselect', lookup: 'permissions', colSpan: 2 },
        { name: 'is_active', label: 'Active', type: 'checkbox', default: true },
      ]}
      fields={[
        { name: 'name', label: 'Role name', required: true },
        { name: 'slug', label: 'Slug', required: true, placeholder: 'e.g. regional-manager' },
        { name: 'description', label: 'Description', colSpan: 2 },
        { name: 'approval_limit', label: 'Approval limit', type: 'number' },
        { name: 'permission_ids', label: 'Permissions', type: 'multiselect', lookup: 'permissions', colSpan: 2 },
      ]}
    />
  )
}
