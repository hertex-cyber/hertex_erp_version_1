import { Link } from 'react-router-dom'
import { Activity, FileText, FolderKanban, Paperclip } from 'lucide-react'
import { Status } from '../../components/cells'
import { dateCol, makePage, refCol, refField, selectField, statusCol } from './projects'

const entities = ['project', 'work_item', 'milestone', 'risk', 'issue', 'change_request']

export const CommentsPage = makePage({
  title: 'Comments',
  eyebrow: 'Projects',
  description: 'Discussion linked to projects and work items. Editing is restricted to the author by the backend.',
  endpoint: '/projects/comments',
  permission: 'projects.comment',
  emptyIcon: FileText,
  columns: [
    { key: 'entity', label: 'Entity', render: (row) => <span className="text-xs text-muted">{row.entity_type} · {String(row.entity_id ?? '').slice(0, 8)}</span> },
    { key: 'body', label: 'Comment', render: (row) => <span className="line-clamp-2 text-xs text-ink-soft">{row.body}</span> },
    refCol('author_id', 'Author', 'users'),
    refCol('parent_comment_id', 'Reply to', 'comments'),
    statusCol(),
    dateCol('created_at', 'Posted'),
  ],
  fields: [
    selectField('entity_type', 'Entity type', entities, 'project', true),
    { name: 'entity_id', label: 'Entity ID', required: true },
    { name: 'body', label: 'Comment', type: 'textarea', required: true },
    { name: 'mentions_json', label: 'Mentions JSON', type: 'json', help: 'Array of user IDs.' },
    refField('parent_comment_id', 'Parent comment', 'comments'),
  ],
  filters: [
    { name: 'entity_type', label: 'All entity types', options: entities },
    { name: 'status', label: 'All statuses', options: ['active', 'archived'] },
  ],
  rowActions: () => [
    {
      label: 'Open project',
      show: (row) => row.entity_type === 'project' && Boolean(row.entity_id),
      render: (row) => (
        <Link
          to={`/projects/projects/${row.entity_id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
    {
      label: 'Open work item project',
      show: (row) => row.entity_type === 'work_item' && Boolean(row.project_id),
      render: (row) => (
        <Link
          to={`/projects/projects/${row.project_id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
  ],
})

export const AttachmentsPage = makePage({
  title: 'Attachments',
  eyebrow: 'Projects',
  description: 'Files remain in the Documents module; records here only store document IDs.',
  endpoint: '/projects/attachments',
  permission: 'projects.attachment',
  emptyIcon: Paperclip,
  columns: [
    { key: 'entity', label: 'Entity', render: (row) => <span className="text-xs text-muted">{row.entity_type} · {String(row.entity_id ?? '').slice(0, 8)}</span> },
    { key: 'title', label: 'Title', render: (row) => (
      <span className="flex items-center gap-2">
        {row.title ?? 'Untitled'}
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted">Documents ID</span>
      </span>
    ) },
    { key: 'document_id', label: 'Document ID', render: (row) => <span className="font-mono text-xs">{String(row.document_id ?? '').slice(0, 8)}</span> },
    statusCol(),
    dateCol('created_at', 'Linked'),
  ],
  fields: [
    selectField('entity_type', 'Entity type', entities, 'project', true),
    { name: 'entity_id', label: 'Entity ID', required: true },
    { name: 'document_id', label: 'Documents ID', required: true, help: 'Upload the file in Documents and paste its ID here.' },
    { name: 'title', label: 'Title' },
    selectField('status', 'Status', ['active', 'archived'], 'active'),
  ],
  filters: [{ name: 'entity_type', label: 'All entity types', options: entities }],
  rowActions: () => [
    {
      label: 'Open project',
      show: (row) => row.entity_type === 'project' && Boolean(row.entity_id),
      render: (row) => (
        <Link
          to={`/projects/projects/${row.entity_id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
  ],
})

export const ActivityPage = makePage({
  title: 'Activity',
  eyebrow: 'Projects',
  description: 'Append-only audit trail for project entities and notifications.',
  endpoint: '/projects/activities',
  permission: 'projects.activity',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: Activity,
  columns: [
    { key: 'entity', label: 'Entity', render: (row) => <span className="text-xs text-muted">{row.entity_type} · {String(row.entity_id ?? '').slice(0, 8)}</span> },
    { key: 'action', label: 'Action', render: (row) => <Status value={row.action} /> },
    refCol('actor_id', 'Actor', 'users'),
    { key: 'changes_json', label: 'Changes', render: (row) => <span className="font-mono text-xs">{JSON.stringify(row.changes_json ?? {})}</span> },
    { key: 'correlation_id', label: 'Correlation', render: (row) => <span className="font-mono text-[11px] text-muted">{row.correlation_id ?? '—'}</span> },
    dateCol('created_at', 'Recorded'),
  ],
  fields: [],
  filters: [{ name: 'entity_type', label: 'All entity types', options: entities }],
  rowActions: () => [
    {
      label: 'Open project',
      show: (row) => row.entity_type === 'project' && Boolean(row.entity_id),
      render: (row) => (
        <Link
          to={`/projects/projects/${row.entity_id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
  ],
})
