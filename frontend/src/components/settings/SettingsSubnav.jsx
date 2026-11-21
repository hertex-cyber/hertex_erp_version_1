import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/format'

export const SETTINGS_LINKS = [
  { to: '/settings', label: 'Hub', end: true },
  { to: '/settings/organisation', label: 'Organisation' },
  { to: '/settings/localisation', label: 'Localisation' },
  { to: '/settings/modules', label: 'Modules & features' },
  { to: '/settings/values', label: 'All settings' },
  { to: '/settings/numbering', label: 'Numbering' },
  { to: '/settings/numbering/gaps', label: 'Gaps' },
  { to: '/settings/numbering/blocks', label: 'Blocks' },
  { to: '/settings/secrets', label: 'Secrets' },
  { to: '/settings/history', label: 'History' },
  { to: '/settings/users', label: 'Team' },
  { to: '/settings/roles', label: 'Roles' },
  { to: '/settings/security', label: 'Security' },
]

export default function SettingsSubnav() {
  return (
    <nav className="-mx-4 mb-5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" data-testid="settings-subnav" aria-label="Settings sections">
      <div className="flex min-w-max gap-1.5">
        {SETTINGS_LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              cn(
                'whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-semibold transition',
                isActive
                  ? 'border-primary/50 bg-primary-soft text-primary'
                  : 'border-line bg-surface text-muted hover:border-primary/30 hover:text-ink',
              )
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
